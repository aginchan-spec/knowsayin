from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from openai import OpenAI

from .config import PROJECT_ROOT
from .credit_game import evaluate_credit_answer
from .model_config import APP_NAME, APP_VERSION, DEFAULT_OPTIMIZE_PROMPT
from .optimizer import _optimize_user_message


DATA_PATH = Path(os.getenv("KNOWSAYIN_API_DATA_PATH") or PROJECT_ROOT / ".knowsayin-cloud-usage.json")
USAGE_LOG_PATH = Path(os.getenv("KNOWSAYIN_API_USAGE_LOG_PATH") or PROJECT_ROOT / ".knowsayin-service-events.jsonl")
MAX_BODY_BYTES = 96 * 1024
usage_lock = threading.RLock()


@dataclass(frozen=True)
class CloudSettings:
    quota_capacity: int
    quota_refill_seconds: int
    token_minute_limit: int
    ip_hour_limit: int
    global_daily_limit: int
    max_chars: int
    allowed_origins: tuple[str, ...]
    token_secret: str
    upstream_base_url: str
    upstream_model: str
    upstream_api_key: str
    download_url: str
    github_url: str
    extra_url: str
    grant_secret: str
    admin_secret: str
    credit_game_cooldown_seconds: int
    usage_log_path: Path


@dataclass(frozen=True)
class AccessContext:
    token_hash: str
    ip_hash: str
    remaining: int
    quota_limit: int
    refill_seconds: int
    refill_at: str
    minute_count: int
    ip_hour_count: int
    device_code: str
    extra_url: str


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the KnowSayin cloud API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8788, type=int)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), KnowSayinCloudHandler)
    print(f"KnowSayin API running at http://{args.host}:{args.port}")
    server.serve_forever()


class KnowSayinCloudHandler(BaseHTTPRequestHandler):
    server_version = "KnowSayinCloud/0.1"

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_common_headers("application/json; charset=utf-8")
        self.end_headers()

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        if path == "/v1/health":
            self._send_json({"ok": True, "name": APP_NAME, "version": APP_VERSION})
            return
        if path == "/v1/config":
            settings = _load_settings()
            self._send_json(
                {
                    "name": APP_NAME,
                    "version": APP_VERSION,
                    "latestVersion": APP_VERSION,
                    "maxChars": settings.max_chars,
                    "anonymousDailyLimit": settings.quota_capacity,
                    "quotaLimit": settings.quota_capacity,
                    "quotaRefillSeconds": settings.quota_refill_seconds,
                    "extraUrl": settings.extra_url,
                    "downloadUrl": settings.download_url,
                    "githubUrl": settings.github_url,
                    "creditGameCooldownSeconds": settings.credit_game_cooldown_seconds,
                }
            )
            return
        if path == "/v1/admin/usage-stats":
            self._handle_admin_usage_stats(parsed_url.query)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/v1/session":
            self._handle_session()
            return
        if path == "/v1/usage":
            self._handle_usage()
            return
        if path == "/v1/clean":
            self._handle_clean()
            return
        if path == "/v1/grant":
            self._handle_grant()
            return
        if path == "/v1/credit-game":
            self._handle_credit_game()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:
        safe_path = urlparse(self.path).path
        settings = _load_settings()
        client_hash = _hash_ip(_client_ip(self), settings.token_secret)
        print(f"client:{client_hash} - {self.command} {safe_path} - {format % args}")

    def _handle_session(self) -> None:
        if self._read_json_body(allow_empty=True) is None:
            return
        settings = _load_settings()
        token = secrets.token_urlsafe(32)
        token_hash = _hash_value(token)
        device_code = _device_code_for_token_hash(token_hash)
        with usage_lock:
            payload = _read_data_file()
            sessions = payload.setdefault("sessions", {})
            sessions[token_hash] = {"createdAt": _now_iso(), "deviceCode": device_code}
            _write_data_file(payload)
        _log_usage_event(
            self,
            settings,
            "session_created",
            device_code=device_code,
            remaining=settings.quota_capacity,
            quota_limit=settings.quota_capacity,
        )
        self._send_json(
            {
                "token": token,
                "dailyLimit": settings.quota_capacity,
                "quotaLimit": settings.quota_capacity,
                "remaining": settings.quota_capacity,
                "refillSeconds": settings.quota_refill_seconds,
                "deviceCode": device_code,
                "extraUrl": _extra_url(settings, device_code),
                "plan": "free",
                "maxChars": settings.max_chars,
            }
        )

    def _handle_usage(self) -> None:
        access = self._resolve_access()
        if isinstance(access, tuple):
            _log_usage_event(self, _load_settings(), "usage_rejected", status="error", error=access[0].get("error"))
            self._send_json(access[0], access[1])
            return
        settings = _load_settings()
        _log_usage_event(
            self,
            settings,
            "usage_checked",
            device_code=access.device_code,
            remaining=access.remaining,
            quota_limit=access.quota_limit,
        )
        self._send_json(
            {
                "remaining": access.remaining,
                "dailyLimit": access.quota_limit,
                "quotaLimit": access.quota_limit,
                "refillSeconds": access.refill_seconds,
                "refillAt": access.refill_at,
                "resetAt": access.refill_at,
                "deviceCode": access.device_code,
                "extraUrl": access.extra_url,
                "plan": "free",
                "maxChars": settings.max_chars,
            }
        )

    def _handle_clean(self) -> None:
        payload = self._read_json_body()
        if payload is None:
            return

        text = str(payload.get("text") or "").strip()
        mode = str(payload.get("mode") or "medium").strip()
        if mode not in {"light", "medium", "strong"}:
            mode = "medium"

        settings = _load_settings()
        if not text:
            _log_usage_event(self, settings, "clean_rejected", status="error", error="EMPTY_TEXT", chars=0)
            self._send_json({"error": "EMPTY_TEXT", "message": "请输入要优化的文字。"}, HTTPStatus.BAD_REQUEST)
            return
        if len(text) > settings.max_chars:
            _log_usage_event(
                self,
                settings,
                "clean_rejected",
                status="error",
                error="TEXT_TOO_LONG",
                chars=len(text),
            )
            self._send_json(
                {
                    "error": "TEXT_TOO_LONG",
                    "message": f"单次最多 {settings.max_chars} 字。",
                    "maxChars": settings.max_chars,
                },
                HTTPStatus.BAD_REQUEST,
            )
            return

        access = self._resolve_access()
        if isinstance(access, tuple):
            _log_usage_event(
                self,
                settings,
                "clean_rejected",
                status="error",
                error=access[0].get("error"),
                chars=len(text),
            )
            self._send_json(access[0], access[1])
            return
        if access.remaining <= 0:
            _log_usage_event(
                self,
                settings,
                "clean_rejected",
                status="error",
                error="QUOTA_EMPTY",
                device_code=access.device_code,
                chars=len(text),
                remaining=0,
                quota_limit=access.quota_limit,
            )
            self._send_json(
                {
                    "error": "QUOTA_EMPTY",
                    "message": "Free quota is empty. Get extra or wait for it to refill.",
                    "remaining": 0,
                    "dailyLimit": access.quota_limit,
                    "quotaLimit": access.quota_limit,
                    "refillSeconds": access.refill_seconds,
                    "refillAt": access.refill_at,
                    "resetAt": access.refill_at,
                    "deviceCode": access.device_code,
                    "extraUrl": access.extra_url,
                    "plan": "free",
                    "maxChars": settings.max_chars,
                },
                HTTPStatus.TOO_MANY_REQUESTS,
            )
            return
        if access.minute_count >= settings.token_minute_limit or access.ip_hour_count >= settings.ip_hour_limit:
            _log_usage_event(
                self,
                settings,
                "clean_rejected",
                status="error",
                error="RATE_LIMITED",
                device_code=access.device_code,
                chars=len(text),
                remaining=access.remaining,
                quota_limit=access.quota_limit,
            )
            self._send_json({"error": "RATE_LIMITED", "message": "请求太频繁，请稍后再试。"}, HTTPStatus.TOO_MANY_REQUESTS)
            return
        if _global_daily_count() >= settings.global_daily_limit:
            _log_usage_event(
                self,
                settings,
                "clean_rejected",
                status="error",
                error="GLOBAL_LIMIT",
                device_code=access.device_code,
                chars=len(text),
                remaining=access.remaining,
                quota_limit=access.quota_limit,
            )
            self._send_json({"error": "GLOBAL_LIMIT", "message": "今日全站额度已用完。"}, HTTPStatus.TOO_MANY_REQUESTS)
            return

        try:
            result = _call_upstream(text, mode, settings)
        except Exception:
            _log_usage_event(
                self,
                settings,
                "clean_failed",
                status="error",
                error="UPSTREAM_FAILED",
                device_code=access.device_code,
                chars=len(text),
                remaining=access.remaining,
                quota_limit=access.quota_limit,
            )
            self._send_json(
                {"error": "UPSTREAM_FAILED", "message": "云端优化失败，请稍后再试。"},
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return

        usage = _increment_usage(
            access.token_hash,
            access.ip_hash,
            len(text),
            settings,
        )
        _log_usage_event(
            self,
            settings,
            "clean_succeeded",
            device_code=access.device_code,
            chars=len(text),
            result_chars=len(result),
            remaining=usage["remaining"],
            quota_limit=access.quota_limit,
        )
        self._send_json(
            {
                "result": result,
                "remaining": usage["remaining"],
                "dailyLimit": access.quota_limit,
                "quotaLimit": access.quota_limit,
                "refillSeconds": access.refill_seconds,
                "refillAt": usage["refillAt"],
                "resetAt": usage["refillAt"],
                "deviceCode": access.device_code,
                "extraUrl": access.extra_url,
                "plan": "free",
                "maxChars": settings.max_chars,
            }
        )

    def _handle_grant(self) -> None:
        payload = self._read_json_body()
        if payload is None:
            return

        settings = _load_settings()
        if not settings.grant_secret:
            _log_usage_event(self, settings, "grant_rejected", status="error", error="EXTRA_DISABLED")
            self._send_json({"error": "EXTRA_DISABLED"}, HTTPStatus.SERVICE_UNAVAILABLE)
            return

        submitted_secret = _bearer_token(self.headers.get("Authorization", "")) or str(
            payload.get("grantSecret") or "",
        ).strip()
        if not hmac.compare_digest(submitted_secret, settings.grant_secret):
            _log_usage_event(self, settings, "grant_rejected", status="error", error="BAD_GRANT_SECRET")
            self._send_json({"error": "BAD_GRANT_SECRET"}, HTTPStatus.UNAUTHORIZED)
            return

        device_code = _normalize_device_code(str(payload.get("deviceCode") or ""))
        if not device_code:
            _log_usage_event(self, settings, "grant_rejected", status="error", error="BAD_DEVICE_CODE")
            self._send_json({"error": "BAD_DEVICE_CODE"}, HTTPStatus.BAD_REQUEST)
            return

        with usage_lock:
            data = _read_data_file()
            sessions = data.setdefault("sessions", {})
            for token_hash, session in sessions.items():
                if not isinstance(session, dict):
                    continue
                if _normalize_device_code(str(session.get("deviceCode") or "")) == device_code:
                    tokens = data.setdefault("tokens", {})
                    token_usage = tokens.get(token_hash) or {}
                    token_usage["balance"] = float(settings.quota_capacity)
                    token_usage["quotaUpdatedAt"] = _now_iso()
                    token_usage["extraCount"] = int(token_usage.get("extraCount") or 0) + 1
                    token_usage["lastExtraAt"] = _now_iso()
                    tokens[token_hash] = token_usage
                    session["lastExtraAt"] = token_usage["lastExtraAt"]
                    _write_data_file(data)
                    _log_usage_event(
                        self,
                        settings,
                        "grant_succeeded",
                        device_code=device_code,
                        remaining=settings.quota_capacity,
                        quota_limit=settings.quota_capacity,
                    )
                    self._send_json(
                        {
                            "ok": True,
                            "deviceCode": device_code,
                            "remaining": settings.quota_capacity,
                            "dailyLimit": settings.quota_capacity,
                            "quotaLimit": settings.quota_capacity,
                            "refillSeconds": settings.quota_refill_seconds,
                            "plan": "free",
                        }
                    )
                    return

        _log_usage_event(
            self,
            settings,
            "grant_rejected",
            status="error",
            error="DEVICE_NOT_FOUND",
            device_code=device_code,
        )
        self._send_json({"error": "DEVICE_NOT_FOUND"}, HTTPStatus.NOT_FOUND)

    def _handle_credit_game(self) -> None:
        payload = self._read_json_body()
        if payload is None:
            return

        question_id = str(payload.get("questionId") or "").strip()
        answer = str(payload.get("answer") or "").strip()
        correct = evaluate_credit_answer(question_id, answer)
        settings = _load_settings()
        if correct is None:
            _log_usage_event(
                self,
                settings,
                "credit_game_rejected",
                status="error",
                error="BAD_CREDIT_QUESTION",
            )
            self._send_json(
                {
                    "error": "BAD_CREDIT_QUESTION",
                    "message": "That quick credit question is not available.",
                },
                HTTPStatus.BAD_REQUEST,
            )
            return

        access = self._resolve_access()
        if isinstance(access, tuple):
            _log_usage_event(
                self,
                settings,
                "credit_game_rejected",
                status="error",
                error=access[0].get("error"),
            )
            self._send_json(access[0], access[1])
            return

        result = _apply_credit_game_result(access.token_hash, settings, correct)
        if result.get("cooldown"):
            _log_usage_event(
                self,
                settings,
                "credit_game_rejected",
                status="error",
                error="CREDIT_GAME_COOLDOWN",
                device_code=access.device_code,
                remaining=result.get("remaining"),
                quota_limit=access.quota_limit,
            )
            self._send_json(
                {
                    "error": "CREDIT_GAME_COOLDOWN",
                    "message": "Quick credit is cooling down.",
                    "remaining": result["remaining"],
                    "dailyLimit": access.quota_limit,
                    "quotaLimit": access.quota_limit,
                    "refillSeconds": access.refill_seconds,
                    "refillAt": result["refillAt"],
                    "resetAt": result["refillAt"],
                    "nextPlayAt": result["nextPlayAt"],
                    "deviceCode": access.device_code,
                    "extraUrl": access.extra_url,
                    "plan": "free",
                    "maxChars": settings.max_chars,
                },
                HTTPStatus.TOO_MANY_REQUESTS,
            )
            return

        _log_usage_event(
            self,
            settings,
            "credit_game_succeeded",
            device_code=access.device_code,
            questionId=question_id,
            correct=correct,
            delta=result["delta"],
            remaining=result["remaining"],
            quota_limit=access.quota_limit,
        )
        self._send_json(
            {
                "ok": True,
                "correct": correct,
                "delta": result["delta"],
                "remaining": result["remaining"],
                "dailyLimit": access.quota_limit,
                "quotaLimit": access.quota_limit,
                "refillSeconds": access.refill_seconds,
                "refillAt": result["refillAt"],
                "resetAt": result["refillAt"],
                "nextPlayAt": result["nextPlayAt"],
                "deviceCode": access.device_code,
                "extraUrl": access.extra_url,
                "plan": "free",
                "maxChars": settings.max_chars,
            }
        )

    def _handle_admin_usage_stats(self, query: str) -> None:
        settings = _load_settings()
        admin_secret = settings.admin_secret or settings.grant_secret
        if not admin_secret:
            self._send_json({"error": "ADMIN_DISABLED"}, HTTPStatus.SERVICE_UNAVAILABLE)
            return

        submitted_secret = _bearer_token(self.headers.get("Authorization", ""))
        if not hmac.compare_digest(submitted_secret, admin_secret):
            self._send_json({"error": "BAD_ADMIN_SECRET"}, HTTPStatus.UNAUTHORIZED)
            return

        params = dict(parse_qsl(query, keep_blank_values=True))
        days = _safe_positive_int(params.get("days"), 0)
        self._send_json(_usage_log_stats(settings.usage_log_path, days=days))

    def _resolve_access(self) -> AccessContext | tuple[dict[str, Any], HTTPStatus]:
        token = _bearer_token(self.headers.get("Authorization", ""))
        if not token:
            return {"error": "BAD_TOKEN", "message": "缺少 session token。"}, HTTPStatus.UNAUTHORIZED

        token_hash = _hash_value(token)
        settings = _load_settings()
        ip_hash = _hash_ip(_client_ip(self), settings.token_secret)

        with usage_lock:
            payload = _read_data_file()
            session = payload.get("sessions", {}).get(token_hash)
            if not isinstance(session, dict):
                return {"error": "BAD_TOKEN", "message": "session 已失效，请重新连接。"}, HTTPStatus.UNAUTHORIZED
            device_code = _normalize_device_code(str(session.get("deviceCode") or ""))
            if not device_code:
                device_code = _device_code_for_token_hash(token_hash)
                session["deviceCode"] = device_code
            token_usage = _token_usage(payload, token_hash, settings)
            ip_usage = _ip_usage(payload, ip_hash)
            _write_data_file(payload)

        return AccessContext(
            token_hash=token_hash,
            ip_hash=ip_hash,
            remaining=token_usage["remaining"],
            quota_limit=settings.quota_capacity,
            refill_seconds=settings.quota_refill_seconds,
            refill_at=token_usage["refillAt"],
            minute_count=token_usage["minuteCount"],
            ip_hour_count=ip_usage["hourCount"],
            device_code=device_code,
            extra_url=_extra_url(settings, device_code),
        )

    def _read_json_body(self, allow_empty: bool = False) -> dict[str, Any] | None:
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = 0

        if length <= 0:
            if allow_empty:
                return {}
            self._send_json({"error": "EMPTY_BODY"}, HTTPStatus.BAD_REQUEST)
            return None
        if length > MAX_BODY_BYTES:
            self._send_json({"error": "BODY_TOO_LARGE"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return None

        try:
            raw_body = self.rfile.read(length)
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            self._send_json({"error": "BAD_JSON"}, HTTPStatus.BAD_REQUEST)
            return None
        if not isinstance(payload, dict):
            self._send_json({"error": "BAD_JSON"}, HTTPStatus.BAD_REQUEST)
            return None
        return payload

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_common_headers("application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_common_headers(self, content_type: str) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        origin = self.headers.get("Origin", "")
        allowed = _load_settings().allowed_origins
        if "*" in allowed or origin in allowed:
            self.send_header("Access-Control-Allow-Origin", "*" if "*" in allowed else origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")


def _load_settings() -> CloudSettings:
    return CloudSettings(
        quota_capacity=_env_int("KNOWSAYIN_API_QUOTA_CAPACITY", 20),
        quota_refill_seconds=_env_int("KNOWSAYIN_API_QUOTA_REFILL_SECONDS", 300),
        token_minute_limit=_env_int("KNOWSAYIN_API_TOKEN_MINUTE_LIMIT", 5),
        ip_hour_limit=_env_int("KNOWSAYIN_API_IP_HOUR_LIMIT", 60),
        global_daily_limit=_env_int("KNOWSAYIN_API_GLOBAL_DAILY_LIMIT", 2000),
        max_chars=_env_int("KNOWSAYIN_API_MAX_CHARS", 3000),
        allowed_origins=_env_list("KNOWSAYIN_API_ALLOWED_ORIGINS", "https://knowsayin.com,http://localhost:8787"),
        token_secret=os.getenv("KNOWSAYIN_API_TOKEN_SECRET", "dev-only-change-me"),
        upstream_base_url=os.getenv("KNOWSAYIN_UPSTREAM_BASE_URL", "https://api.deepseek.com/v1").strip(),
        upstream_model=os.getenv("KNOWSAYIN_UPSTREAM_MODEL", "deepseek-chat").strip(),
        upstream_api_key=(os.getenv("KNOWSAYIN_UPSTREAM_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or "").strip(),
        download_url=os.getenv("KNOWSAYIN_DOWNLOAD_URL", "https://knowsayin.com/download").strip(),
        github_url=os.getenv("KNOWSAYIN_GITHUB_URL", "https://github.com/aginchan-spec/knowsayin").strip(),
        extra_url=os.getenv("KNOWSAYIN_EXTRA_URL", "https://knowsayin.com").strip(),
        grant_secret=os.getenv("KNOWSAYIN_API_GRANT_SECRET", "").strip(),
        admin_secret=os.getenv("KNOWSAYIN_API_ADMIN_SECRET", "").strip(),
        credit_game_cooldown_seconds=_env_int("KNOWSAYIN_API_CREDIT_GAME_COOLDOWN_SECONDS", 300),
        usage_log_path=Path(os.getenv("KNOWSAYIN_API_USAGE_LOG_PATH") or USAGE_LOG_PATH),
    )


def _call_upstream(text: str, mode: str, settings: CloudSettings) -> str:
    if not settings.upstream_api_key:
        raise RuntimeError("Missing upstream API key")
    client = OpenAI(api_key=settings.upstream_api_key, base_url=settings.upstream_base_url)
    response = client.chat.completions.create(
        model=settings.upstream_model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": DEFAULT_OPTIMIZE_PROMPT},
            {"role": "user", "content": _optimize_user_message(text, mode)},  # type: ignore[arg-type]
        ],
    )
    result = response.choices[0].message.content or ""
    if not result.strip():
        raise RuntimeError("Empty upstream result")
    return result.strip()


def _log_usage_event(
    handler: BaseHTTPRequestHandler,
    settings: CloudSettings,
    event: str,
    status: str = "ok",
    **fields: Any,
) -> None:
    try:
        ip = _client_ip(handler)
        entry: dict[str, Any] = {
            "ts": _now_iso(),
            "date": _today_key(),
            "event": event,
            "status": status,
            "ip": ip,
            "ipHash": _hash_ip(ip, settings.token_secret),
            "method": handler.command,
            "path": urlparse(handler.path).path,
        }
        user_agent = handler.headers.get("User-Agent", "").strip()
        if user_agent:
            entry["userAgent"] = user_agent[:300]
        aliases = {
            "device_code": "deviceCode",
            "quota_limit": "quotaLimit",
            "result_chars": "resultChars",
        }
        for key, value in fields.items():
            if value is None or value == "":
                continue
            entry[aliases.get(key, key)] = value
        _append_usage_log(settings.usage_log_path, entry)
    except Exception:
        return


def _append_usage_log(path: Path, entry: dict[str, Any]) -> None:
    with usage_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        os.chmod(path, 0o600)


def _usage_log_stats(path: Path, days: int = 0) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days > 0 else None
    stats: dict[str, Any] = {
        "generatedAt": _now_iso(),
        "days": days,
        "logPath": str(path),
        "totals": {
            "events": 0,
            "sessions": 0,
            "usageChecks": 0,
            "cleanRequests": 0,
            "cleanSuccesses": 0,
            "cleanErrors": 0,
            "grants": 0,
            "grantErrors": 0,
            "creditGames": 0,
            "creditGameErrors": 0,
            "submittedChars": 0,
            "optimizedChars": 0,
            "uniqueIps": 0,
            "uniqueDevices": 0,
        },
        "eventsByType": {},
        "byIp": [],
        "byDevice": [],
        "daily": [],
        "malformedLines": 0,
    }
    if not path.exists():
        return stats

    ips: dict[str, dict[str, Any]] = {}
    devices: dict[str, dict[str, Any]] = {}
    daily: dict[str, dict[str, Any]] = {}
    unique_ips: set[str] = set()
    unique_devices: set[str] = set()

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception:
                stats["malformedLines"] += 1
                continue
            if not isinstance(entry, dict):
                stats["malformedLines"] += 1
                continue
            if cutoff is not None:
                timestamp = _parse_iso(str(entry.get("ts") or ""))
                if timestamp is None or timestamp < cutoff:
                    continue
            _accumulate_usage_stats(stats, ips, devices, daily, unique_ips, unique_devices, entry)

    stats["totals"]["uniqueIps"] = len(unique_ips)
    stats["totals"]["uniqueDevices"] = len(unique_devices)
    stats["byIp"] = _finalize_usage_buckets(ips.values(), "devices")
    stats["byDevice"] = _finalize_usage_buckets(devices.values(), "ips")
    stats["daily"] = _finalize_daily_buckets(daily.values())
    return stats


def _accumulate_usage_stats(
    stats: dict[str, Any],
    ips: dict[str, dict[str, Any]],
    devices: dict[str, dict[str, Any]],
    daily: dict[str, dict[str, Any]],
    unique_ips: set[str],
    unique_devices: set[str],
    entry: dict[str, Any],
) -> None:
    event = str(entry.get("event") or "unknown")
    status = str(entry.get("status") or "")
    ip = str(entry.get("ip") or "")
    device_code = _normalize_device_code(str(entry.get("deviceCode") or entry.get("device_code") or ""))
    date = str(entry.get("date") or "") or _date_from_timestamp(str(entry.get("ts") or ""))
    chars = _safe_positive_int(entry.get("chars"), 0)

    totals = stats["totals"]
    stats["eventsByType"][event] = int(stats["eventsByType"].get(event) or 0) + 1

    if ip:
        unique_ips.add(ip)
    if device_code:
        unique_devices.add(device_code)

    for bucket in (
        _usage_bucket(ips, ip, "ip") if ip else None,
        _usage_bucket(devices, device_code, "deviceCode") if device_code else None,
        _usage_bucket(daily, date, "date") if date else None,
    ):
        if bucket is None:
            continue
        _increment_bucket(bucket, event, status, chars, entry)
        if ip and bucket.get("date"):
            bucket["_ips"].add(ip)
        if device_code and bucket.get("date"):
            bucket["_devices"].add(device_code)
        if ip and bucket.get("deviceCode"):
            bucket["_ips"].add(ip)
        if device_code and bucket.get("ip"):
            bucket["_devices"].add(device_code)

    _increment_bucket(totals, event, status, chars, entry)


def _usage_bucket(buckets: dict[str, dict[str, Any]], key: str, key_name: str) -> dict[str, Any]:
    bucket = buckets.get(key)
    if bucket is None:
        bucket = {
            key_name: key,
            "events": 0,
            "sessions": 0,
            "usageChecks": 0,
            "cleanRequests": 0,
            "cleanSuccesses": 0,
            "cleanErrors": 0,
            "grants": 0,
            "grantErrors": 0,
            "creditGames": 0,
            "creditGameErrors": 0,
            "submittedChars": 0,
            "optimizedChars": 0,
            "firstSeenAt": "",
            "lastSeenAt": "",
            "_ips": set(),
            "_devices": set(),
        }
        buckets[key] = bucket
    return bucket


def _increment_bucket(bucket: dict[str, Any], event: str, status: str, chars: int, entry: dict[str, Any]) -> None:
    bucket["events"] = int(bucket.get("events") or 0) + 1
    if event == "session_created":
        bucket["sessions"] = int(bucket.get("sessions") or 0) + 1
    elif event == "usage_checked":
        bucket["usageChecks"] = int(bucket.get("usageChecks") or 0) + 1
    elif event.startswith("clean_"):
        bucket["cleanRequests"] = int(bucket.get("cleanRequests") or 0) + 1
        bucket["submittedChars"] = int(bucket.get("submittedChars") or 0) + chars
        if event == "clean_succeeded":
            bucket["cleanSuccesses"] = int(bucket.get("cleanSuccesses") or 0) + 1
            bucket["optimizedChars"] = int(bucket.get("optimizedChars") or 0) + chars
        elif status == "error":
            bucket["cleanErrors"] = int(bucket.get("cleanErrors") or 0) + 1
    elif event == "grant_succeeded":
        bucket["grants"] = int(bucket.get("grants") or 0) + 1
    elif event.startswith("grant_") and status == "error":
        bucket["grantErrors"] = int(bucket.get("grantErrors") or 0) + 1
    elif event == "credit_game_succeeded":
        bucket["creditGames"] = int(bucket.get("creditGames") or 0) + 1
    elif event.startswith("credit_game_") and status == "error":
        bucket["creditGameErrors"] = int(bucket.get("creditGameErrors") or 0) + 1

    if entry.get("remaining") is not None:
        bucket["lastRemaining"] = entry.get("remaining")
    quota_limit = entry.get("quotaLimit") if entry.get("quotaLimit") is not None else entry.get("quota_limit")
    if quota_limit is not None:
        bucket["quotaLimit"] = quota_limit
    _touch_bucket(bucket, str(entry.get("ts") or ""))


def _touch_bucket(bucket: dict[str, Any], timestamp: str) -> None:
    if not timestamp:
        return
    if not bucket.get("firstSeenAt") or timestamp < bucket["firstSeenAt"]:
        bucket["firstSeenAt"] = timestamp
    if not bucket.get("lastSeenAt") or timestamp > bucket["lastSeenAt"]:
        bucket["lastSeenAt"] = timestamp


def _finalize_usage_buckets(buckets: Any, related_key: str) -> list[dict[str, Any]]:
    finalized = []
    private_key = f"_{related_key}"
    for bucket in buckets:
        item = {key: value for key, value in bucket.items() if not key.startswith("_")}
        item[related_key] = sorted(bucket.get(private_key, set()))
        finalized.append(item)
    return sorted(
        finalized,
        key=lambda item: (
            -int(item.get("cleanSuccesses") or 0),
            -int(item.get("events") or 0),
            str(item.get("ip") or item.get("deviceCode") or item.get("date") or ""),
        ),
    )


def _finalize_daily_buckets(buckets: Any) -> list[dict[str, Any]]:
    finalized = []
    for bucket in buckets:
        item = {key: value for key, value in bucket.items() if not key.startswith("_")}
        item["uniqueIps"] = len(bucket.get("_ips", set()))
        item["uniqueDevices"] = len(bucket.get("_devices", set()))
        finalized.append(item)
    return sorted(finalized, key=lambda item: str(item.get("date") or ""))


def _read_data_file() -> dict[str, Any]:
    if not DATA_PATH.exists():
        return _empty_data()
    try:
        payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return _empty_data()
    if payload.get("date") != _today_key():
        sessions = payload.get("sessions") if isinstance(payload.get("sessions"), dict) else {}
        tokens = payload.get("tokens") if isinstance(payload.get("tokens"), dict) else {}
        return {**_empty_data(), "sessions": sessions, "tokens": tokens}
    for key in ("sessions", "tokens", "ips"):
        if not isinstance(payload.get(key), dict):
            payload[key] = {}
    return payload


def _write_data_file(payload: dict[str, Any]) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = DATA_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(tmp_path, 0o600)
    tmp_path.replace(DATA_PATH)


def _empty_data() -> dict[str, Any]:
    return {"date": _today_key(), "sessions": {}, "tokens": {}, "ips": {}, "global": {"count": 0, "chars": 0}}


def _token_usage(payload: dict[str, Any], token_hash: str, settings: CloudSettings) -> dict[str, Any]:
    current_minute = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    tokens = payload.setdefault("tokens", {})
    usage = tokens.get(token_hash) or {}
    balance, refill_at = _refill_quota_balance(usage, settings)
    usage["balance"] = balance
    usage["quotaUpdatedAt"] = _now_iso()
    tokens[token_hash] = usage
    return {
        "count": int(usage.get("count") or 0),
        "remaining": int(balance),
        "refillAt": refill_at,
        "minuteCount": int(usage.get("minuteCount") or 0) if usage.get("minute") == current_minute else 0,
    }


def _ip_usage(payload: dict[str, Any], ip_hash: str) -> dict[str, int]:
    current_hour = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
    usage = payload.get("ips", {}).get(ip_hash) or {}
    return {
        "hourCount": int(usage.get("hourCount") or 0) if usage.get("hour") == current_hour else 0,
    }


def _increment_usage(
    token_hash: str,
    ip_hash: str,
    chars: int,
    settings: CloudSettings,
) -> dict[str, Any]:
    with usage_lock:
        payload = _read_data_file()
        current_minute = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
        current_hour = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")

        tokens = payload.setdefault("tokens", {})
        token_usage = tokens.get(token_hash) or {"count": 0, "chars": 0}
        balance, _ = _refill_quota_balance(token_usage, settings)
        if balance >= 1:
            balance -= 1
        token_usage["balance"] = balance
        token_usage["quotaUpdatedAt"] = _now_iso()
        token_usage["count"] = int(token_usage.get("count") or 0) + 1
        token_usage["chars"] = int(token_usage.get("chars") or 0) + chars
        token_usage["minuteCount"] = (
            int(token_usage.get("minuteCount") or 0) + 1
            if token_usage.get("minute") == current_minute
            else 1
        )
        token_usage["minute"] = current_minute
        tokens[token_hash] = token_usage

        ips = payload.setdefault("ips", {})
        ip_usage = ips.get(ip_hash) or {"count": 0, "chars": 0}
        ip_usage["count"] = int(ip_usage.get("count") or 0) + 1
        ip_usage["chars"] = int(ip_usage.get("chars") or 0) + chars
        ip_usage["hourCount"] = (
            int(ip_usage.get("hourCount") or 0) + 1 if ip_usage.get("hour") == current_hour else 1
        )
        ip_usage["hour"] = current_hour
        ips[ip_hash] = ip_usage

        global_usage = payload.setdefault("global", {"count": 0, "chars": 0})
        global_usage["count"] = int(global_usage.get("count") or 0) + 1
        global_usage["chars"] = int(global_usage.get("chars") or 0) + chars

        _write_data_file(payload)
        _, refill_at = _refill_quota_balance(token_usage, settings)
        return {
            "count": int(token_usage["count"]),
            "chars": int(token_usage["chars"]),
            "remaining": int(float(token_usage["balance"])),
            "refillAt": refill_at,
        }


def _apply_credit_game_result(token_hash: str, settings: CloudSettings, correct: bool) -> dict[str, Any]:
    with usage_lock:
        payload = _read_data_file()
        tokens = payload.setdefault("tokens", {})
        token_usage = tokens.get(token_hash) or {}
        balance, refill_at = _refill_quota_balance(token_usage, settings)
        now = datetime.now(timezone.utc)
        last_played_at = _parse_iso(str(token_usage.get("lastCreditGameAt") or ""))
        cooldown_seconds = max(settings.credit_game_cooldown_seconds, 0)
        if last_played_at is not None and cooldown_seconds > 0:
            elapsed_seconds = max((now - last_played_at).total_seconds(), 0.0)
            if elapsed_seconds < cooldown_seconds:
                next_play_at = last_played_at + timedelta(seconds=cooldown_seconds)
                token_usage["balance"] = balance
                token_usage["quotaUpdatedAt"] = _now_iso()
                tokens[token_hash] = token_usage
                _write_data_file(payload)
                return {
                    "cooldown": True,
                    "remaining": int(balance),
                    "refillAt": refill_at,
                    "nextPlayAt": next_play_at.isoformat(),
                }

        delta = 1 if correct else -1
        new_balance = max(0.0, min(float(settings.quota_capacity), balance + delta))
        token_usage["balance"] = round(new_balance, 6)
        token_usage["quotaUpdatedAt"] = _now_iso()
        token_usage["lastCreditGameAt"] = token_usage["quotaUpdatedAt"]
        token_usage["creditGameCount"] = int(token_usage.get("creditGameCount") or 0) + 1
        if correct:
            token_usage["creditGameWins"] = int(token_usage.get("creditGameWins") or 0) + 1
        else:
            token_usage["creditGameLosses"] = int(token_usage.get("creditGameLosses") or 0) + 1
        tokens[token_hash] = token_usage
        _write_data_file(payload)

        _, updated_refill_at = _refill_quota_balance(token_usage, settings)
        next_play_at = now + timedelta(seconds=cooldown_seconds)
        return {
            "cooldown": False,
            "delta": delta,
            "remaining": int(float(token_usage["balance"])),
            "refillAt": updated_refill_at,
            "nextPlayAt": next_play_at.isoformat() if cooldown_seconds > 0 else "",
        }


def _refill_quota_balance(usage: dict[str, Any], settings: CloudSettings) -> tuple[float, str]:
    now = datetime.now(timezone.utc)
    capacity = float(settings.quota_capacity)
    try:
        balance = float(usage.get("balance"))
    except (TypeError, ValueError):
        balance = capacity

    updated_at = _parse_iso(str(usage.get("quotaUpdatedAt") or "")) or now
    elapsed_seconds = max((now - updated_at).total_seconds(), 0.0)
    if balance < capacity and settings.quota_refill_seconds > 0:
        balance = min(capacity, balance + (elapsed_seconds / settings.quota_refill_seconds))
    balance = max(0.0, min(capacity, balance))

    if balance >= capacity:
        return round(balance, 6), ""

    next_whole = int(balance) + 1
    seconds_until_next = max((next_whole - balance) * settings.quota_refill_seconds, 0.0)
    refill_at = datetime.fromtimestamp(now.timestamp() + seconds_until_next, tz=timezone.utc).isoformat()
    return round(balance, 6), refill_at


def _global_daily_count() -> int:
    with usage_lock:
        return int(_read_data_file().get("global", {}).get("count") or 0)


def _bearer_token(header: str) -> str:
    prefix = "Bearer "
    if not header.startswith(prefix):
        return ""
    return header[len(prefix) :].strip()


def _client_ip(handler: BaseHTTPRequestHandler) -> str:
    cf_ip = handler.headers.get("CF-Connecting-IP", "").strip()
    if cf_ip:
        return cf_ip
    forwarded = handler.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    return forwarded or handler.client_address[0]


def _hash_ip(ip: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), ip.encode("utf-8"), hashlib.sha256).hexdigest()[:24]


def _hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def _device_code_for_token_hash(token_hash: str) -> str:
    digest = hashlib.sha256(f"knowsayin-device:{token_hash}".encode("utf-8")).digest()
    return base64.b32encode(digest).decode("ascii").rstrip("=")[:8]


def _normalize_device_code(value: str) -> str:
    return "".join(ch for ch in value.upper() if ch.isalnum())[:16]


def _extra_url(settings: CloudSettings, device_code: str) -> str:
    base_url = settings.extra_url or "https://knowsayin.com"
    parsed = urlparse(base_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["machine"] = device_code
    return urlunparse(parsed._replace(query=urlencode(query)))


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _next_reset_iso() -> str:
    now = datetime.now(timezone.utc)
    tomorrow_ts = datetime(now.year, now.month, now.day, tzinfo=timezone.utc).timestamp() + 86400
    return datetime.fromtimestamp(tomorrow_ts, tz=timezone.utc).isoformat()


def _date_from_timestamp(value: str) -> str:
    parsed = _parse_iso(value)
    return parsed.strftime("%Y-%m-%d") if parsed else ""


def _safe_positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def _env_list(name: str, default: str) -> tuple[str, ...]:
    raw = os.getenv(name, default)
    return tuple(item.strip() for item in raw.split(",") if item.strip())


if __name__ == "__main__":
    main()
