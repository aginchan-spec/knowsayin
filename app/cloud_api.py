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
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from openai import OpenAI

from .config import PROJECT_ROOT
from .model_config import APP_NAME, APP_VERSION, DEFAULT_OPTIMIZE_PROMPT
from .optimizer import _optimize_user_message


DATA_PATH = Path(os.getenv("KNOWSAYIN_API_DATA_PATH") or PROJECT_ROOT / ".knowsayin-cloud-usage.json")
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
    upgrade_url: str
    activation_secret: str


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
    upgrade_url: str
    is_activated: bool


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
        path = urlparse(self.path).path
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
                    "upgradeUrl": settings.upgrade_url,
                    "downloadUrl": settings.download_url,
                    "githubUrl": settings.github_url,
                }
            )
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
        if path == "/v1/activate":
            self._handle_activate()
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
        self._send_json(
            {
                "token": token,
                "dailyLimit": settings.quota_capacity,
                "quotaLimit": settings.quota_capacity,
                "remaining": settings.quota_capacity,
                "refillSeconds": settings.quota_refill_seconds,
                "deviceCode": device_code,
                "upgradeUrl": _upgrade_url(settings, device_code),
                "plan": "free",
                "maxChars": settings.max_chars,
            }
        )

    def _handle_usage(self) -> None:
        access = self._resolve_access()
        if isinstance(access, tuple):
            self._send_json(access[0], access[1])
            return
        settings = _load_settings()
        self._send_json(
            {
                "remaining": access.remaining,
                "dailyLimit": access.quota_limit,
                "quotaLimit": access.quota_limit,
                "refillSeconds": access.refill_seconds,
                "refillAt": access.refill_at,
                "resetAt": access.refill_at,
                "deviceCode": access.device_code,
                "upgradeUrl": access.upgrade_url,
                "plan": "paid" if access.is_activated else "free",
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
            self._send_json({"error": "EMPTY_TEXT", "message": "请输入要优化的文字。"}, HTTPStatus.BAD_REQUEST)
            return
        if len(text) > settings.max_chars:
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
            self._send_json(access[0], access[1])
            return
        if not access.is_activated and access.remaining <= 0:
            self._send_json(
                {
                    "error": "QUOTA_EMPTY",
                    "message": "Free quota is empty. Upgrade or wait for it to refill.",
                    "remaining": 0,
                    "dailyLimit": access.quota_limit,
                    "quotaLimit": access.quota_limit,
                    "refillSeconds": access.refill_seconds,
                    "refillAt": access.refill_at,
                    "resetAt": access.refill_at,
                    "deviceCode": access.device_code,
                    "upgradeUrl": access.upgrade_url,
                    "plan": "free",
                    "maxChars": settings.max_chars,
                },
                HTTPStatus.TOO_MANY_REQUESTS,
            )
            return
        if access.minute_count >= settings.token_minute_limit or access.ip_hour_count >= settings.ip_hour_limit:
            self._send_json({"error": "RATE_LIMITED", "message": "请求太频繁，请稍后再试。"}, HTTPStatus.TOO_MANY_REQUESTS)
            return
        if _global_daily_count() >= settings.global_daily_limit:
            self._send_json({"error": "GLOBAL_LIMIT", "message": "今日全站额度已用完。"}, HTTPStatus.TOO_MANY_REQUESTS)
            return

        try:
            result = _call_upstream(text, mode, settings)
        except Exception:
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
            consume_quota=not access.is_activated,
        )
        self._send_json(
            {
                "result": result,
                "remaining": access.quota_limit if access.is_activated else usage["remaining"],
                "dailyLimit": access.quota_limit,
                "quotaLimit": access.quota_limit,
                "refillSeconds": access.refill_seconds,
                "refillAt": usage["refillAt"],
                "resetAt": usage["refillAt"],
                "deviceCode": access.device_code,
                "upgradeUrl": access.upgrade_url,
                "plan": "paid" if access.is_activated else "free",
                "maxChars": settings.max_chars,
            }
        )

    def _handle_activate(self) -> None:
        payload = self._read_json_body()
        if payload is None:
            return

        settings = _load_settings()
        if not settings.activation_secret:
            self._send_json({"error": "ACTIVATION_DISABLED"}, HTTPStatus.SERVICE_UNAVAILABLE)
            return

        submitted_secret = _bearer_token(self.headers.get("Authorization", "")) or str(
            payload.get("activationSecret") or "",
        ).strip()
        if not hmac.compare_digest(submitted_secret, settings.activation_secret):
            self._send_json({"error": "BAD_ACTIVATION_SECRET"}, HTTPStatus.UNAUTHORIZED)
            return

        device_code = _normalize_device_code(str(payload.get("deviceCode") or ""))
        if not device_code:
            self._send_json({"error": "BAD_DEVICE_CODE"}, HTTPStatus.BAD_REQUEST)
            return

        with usage_lock:
            data = _read_data_file()
            sessions = data.setdefault("sessions", {})
            for session in sessions.values():
                if not isinstance(session, dict):
                    continue
                if _normalize_device_code(str(session.get("deviceCode") or "")) == device_code:
                    session["activatedAt"] = _now_iso()
                    _write_data_file(data)
                    self._send_json({"ok": True, "deviceCode": device_code, "plan": "paid"})
                    return

        self._send_json({"error": "DEVICE_NOT_FOUND"}, HTTPStatus.NOT_FOUND)

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
            is_activated = bool(session.get("activatedAt"))
            token_usage = _token_usage(payload, token_hash, settings)
            ip_usage = _ip_usage(payload, ip_hash)
            _write_data_file(payload)

        return AccessContext(
            token_hash=token_hash,
            ip_hash=ip_hash,
            remaining=settings.quota_capacity if is_activated else token_usage["remaining"],
            quota_limit=settings.quota_capacity,
            refill_seconds=settings.quota_refill_seconds,
            refill_at=token_usage["refillAt"],
            minute_count=token_usage["minuteCount"],
            ip_hour_count=ip_usage["hourCount"],
            device_code=device_code,
            upgrade_url=_upgrade_url(settings, device_code),
            is_activated=is_activated,
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
        quota_capacity=_env_int("KNOWSAYIN_API_QUOTA_CAPACITY", 10),
        quota_refill_seconds=_env_int("KNOWSAYIN_API_QUOTA_REFILL_SECONDS", 600),
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
        upgrade_url=os.getenv("KNOWSAYIN_UPGRADE_URL", "https://knowsayin.com").strip(),
        activation_secret=os.getenv("KNOWSAYIN_API_ACTIVATION_SECRET", "").strip(),
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
    consume_quota: bool = True,
) -> dict[str, Any]:
    with usage_lock:
        payload = _read_data_file()
        current_minute = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
        current_hour = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")

        tokens = payload.setdefault("tokens", {})
        token_usage = tokens.get(token_hash) or {"count": 0, "chars": 0}
        balance, _ = _refill_quota_balance(token_usage, settings)
        if consume_quota and balance >= 1:
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


def _upgrade_url(settings: CloudSettings, device_code: str) -> str:
    base_url = settings.upgrade_url or "https://knowsayin.com"
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
