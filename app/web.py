from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import PROJECT_ROOT
from .optimizer import optimize_prompt


WEB_ROOT = PROJECT_ROOT / "web"
USAGE_PATH = PROJECT_ROOT / ".justsaying-web-usage.json"
MAX_BODY_BYTES = 96 * 1024


@dataclass(frozen=True)
class WebSettings:
    require_pass: bool
    default_daily_limit: int
    default_max_chars: int
    global_daily_limit: int
    site_url: str
    base_path: str


@dataclass(frozen=True)
class PassConfig:
    label: str
    token: str
    daily_limit: int
    max_chars: int
    enabled: bool = True


@dataclass(frozen=True)
class AccessContext:
    key: str
    label: str
    daily_limit: int
    max_chars: int
    remaining: int
    is_local_dev: bool = False


usage_lock = threading.RLock()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Just Saying mobile web app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8787, type=int)
    parser.add_argument("--make-pass", metavar="LABEL", help="Generate a friend pass config line.")
    parser.add_argument("--daily-limit", default=100, type=int)
    parser.add_argument("--max-chars", default=3000, type=int)
    parser.add_argument("--base-url", default="https://mehelper.com/justsaying")
    args = parser.parse_args()

    if args.make_pass:
        token = secrets.token_urlsafe(24)
        print(f"JUSTSAYING_WEB_PASSES='{args.make_pass}:{token}:{args.daily_limit}:{args.max_chars}:true'")
        print(f"Friend link: {args.base_url.rstrip('/')}/p/{token}")
        return

    server = ThreadingHTTPServer((args.host, args.port), JustSayingWebHandler)
    print(f"Just Saying web running at http://{args.host}:{args.port}")
    server.serve_forever()


class JustSayingWebHandler(BaseHTTPRequestHandler):
    server_version = "JustSayingWeb/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        base_path, path = _route_path(parsed.path)

        if path == "/health":
            self._send_json({"ok": True})
            return

        if path == "/" or path.startswith("/p/"):
            self._send_index(base_path)
            return

        if path == "/manifest.webmanifest":
            self._send_manifest(base_path)
            return

        if path.startswith("/static/"):
            relative = path.removeprefix("/static/")
            self._send_static(relative)
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        _, path = _route_path(parsed.path)
        if path == "/api/clean":
            self._handle_clean()
            return
        if path == "/api/usage":
            self._handle_usage()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:
        safe_path = urlparse(self.path).path
        _, safe_path = _route_path(safe_path)
        if safe_path.startswith("/p/"):
            safe_path = "/p/<pass>"
        print(f"{self.address_string()} - {self.command} {safe_path} - {format % args}")

    def _handle_clean(self) -> None:
        payload = self._read_json_body()
        if payload is None:
            return

        text = str(payload.get("text") or "").strip()
        mode = str(payload.get("mode") or "medium").strip()
        token = str(payload.get("pass") or "").strip()

        if not text:
            self._send_json({"error": "EMPTY_TEXT", "message": "请输入要优化的文字。"}, HTTPStatus.BAD_REQUEST)
            return
        if mode not in {"light", "medium", "strong"}:
            mode = "medium"

        access = self._resolve_access(token)
        if isinstance(access, tuple):
            self._send_json(access[0], access[1])
            return

        if len(text) > access.max_chars:
            self._send_json(
                {
                    "error": "TEXT_TOO_LONG",
                    "message": f"单次最多 {access.max_chars} 字。",
                    "maxChars": access.max_chars,
                },
                HTTPStatus.BAD_REQUEST,
            )
            return

        if access.remaining <= 0:
            self._send_json(
                {
                    "error": "DAILY_LIMIT",
                    "message": "今日额度已用完。",
                    "remaining": 0,
                },
                HTTPStatus.TOO_MANY_REQUESTS,
            )
            return

        try:
            result = optimize_prompt(text, mode)  # type: ignore[arg-type]
        except Exception:
            self._send_json(
                {"error": "OPTIMIZE_FAILED", "message": "优化失败，请稍后再试。"},
                HTTPStatus.BAD_GATEWAY,
            )
            return

        usage = _increment_usage(access.key, len(text))
        self._send_json(
            {
                "result": result,
                "remaining": max(access.daily_limit - usage["count"], 0),
                "dailyLimit": access.daily_limit,
                "maxChars": access.max_chars,
            }
        )

    def _handle_usage(self) -> None:
        payload = self._read_json_body()
        if payload is None:
            return
        token = str(payload.get("pass") or "").strip()
        access = self._resolve_access(token)
        if isinstance(access, tuple):
            self._send_json(access[0], access[1])
            return
        self._send_json(
            {
                "remaining": access.remaining,
                "dailyLimit": access.daily_limit,
                "maxChars": access.max_chars,
                "label": access.label,
            }
        )

    def _resolve_access(self, token: str) -> AccessContext | tuple[dict[str, Any], HTTPStatus]:
        settings = _load_web_settings()
        passes = _load_passes(settings)
        is_local = self.client_address[0] in {"127.0.0.1", "::1", "localhost"}

        if not passes and is_local:
            key = "local-dev"
            usage = _get_usage(key)
            remaining = max(settings.default_daily_limit - usage["count"], 0)
            return AccessContext(
                key=key,
                label="local",
                daily_limit=settings.default_daily_limit,
                max_chars=settings.default_max_chars,
                remaining=remaining,
                is_local_dev=True,
            )

        if not token:
            return (
                {"error": "PASS_REQUIRED", "message": "请输入访问口令或使用朋友专属链接。"},
                HTTPStatus.UNAUTHORIZED,
            )

        pass_config = passes.get(token)
        if not pass_config or not pass_config.enabled:
            return (
                {"error": "PASS_INVALID", "message": "访问口令无效或已停用。"},
                HTTPStatus.FORBIDDEN,
            )

        key = _hash_token(token)
        usage = _get_usage(key)
        global_usage = _get_usage("__global__")
        if global_usage["count"] >= settings.global_daily_limit:
            return (
                {"error": "GLOBAL_LIMIT", "message": "今日全站免费额度已用完。"},
                HTTPStatus.TOO_MANY_REQUESTS,
            )

        remaining = max(pass_config.daily_limit - usage["count"], 0)
        return AccessContext(
            key=key,
            label=pass_config.label,
            daily_limit=pass_config.daily_limit,
            max_chars=pass_config.max_chars,
            remaining=remaining,
        )

    def _read_json_body(self) -> dict[str, Any] | None:
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = 0

        if length <= 0:
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

    def _send_static(self, relative: str) -> None:
        static_root = (WEB_ROOT / "static").resolve()
        target = (static_root / relative).resolve()
        if not str(target).startswith(str(static_root)) or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self._send_file(target, content_type)

    def _send_file(self, path: Path, content_type: str) -> None:
        try:
            body = path.read_bytes()
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        self._send_bytes(body, content_type)

    def _send_index(self, base_path: str) -> None:
        try:
            html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        html = html.replace("__BASE_PATH__", base_path)
        self._send_bytes(html.encode("utf-8"), "text/html; charset=utf-8")

    def _send_manifest(self, base_path: str) -> None:
        body = {
            "name": "Just Saying",
            "short_name": "Just Saying",
            "start_url": f"{base_path or '/'}/".replace("//", "/"),
            "display": "standalone",
            "background_color": "#f7f5ef",
            "theme_color": "#f7f5ef",
            "icons": [],
        }
        self._send_bytes(
            json.dumps(body, ensure_ascii=False).encode("utf-8"),
            "application/manifest+json",
        )

    def _send_bytes(self, body: bytes, content_type: str) -> None:
        self.send_response(HTTPStatus.OK)
        self._send_common_headers(content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("Referrer-Policy", "no-referrer")


def _load_web_settings() -> WebSettings:
    from os import getenv

    return WebSettings(
        require_pass=_env_bool("JUSTSAYING_WEB_REQUIRE_PASS", True),
        default_daily_limit=_env_int("JUSTSAYING_WEB_DEFAULT_DAILY_LIMIT", 100),
        default_max_chars=_env_int("JUSTSAYING_WEB_DEFAULT_MAX_CHARS", 3000),
        global_daily_limit=_env_int("JUSTSAYING_WEB_GLOBAL_DAILY_LIMIT", 1000),
        site_url=getenv("JUSTSAYING_WEB_SITE_URL", "https://mehelper.com/justsaying").strip(),
        base_path=_normalize_base_path(getenv("JUSTSAYING_WEB_BASE_PATH", "/justsaying")),
    )


def _load_passes(settings: WebSettings) -> dict[str, PassConfig]:
    from os import getenv

    raw = getenv("JUSTSAYING_WEB_PASSES", "").strip()
    if not raw:
        return {} if settings.require_pass else {}

    passes: dict[str, PassConfig] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        parts = [part.strip() for part in item.split(":")]
        if len(parts) == 1:
            label = "friend"
            token = parts[0]
            daily_limit = settings.default_daily_limit
            max_chars = settings.default_max_chars
            enabled = True
        else:
            label = parts[0] or "friend"
            token = parts[1]
            daily_limit = _safe_int(parts[2], settings.default_daily_limit) if len(parts) > 2 else settings.default_daily_limit
            max_chars = _safe_int(parts[3], settings.default_max_chars) if len(parts) > 3 else settings.default_max_chars
            enabled = parts[4].lower() not in {"0", "false", "no", "off", "disabled"} if len(parts) > 4 else True
        if token:
            passes[token] = PassConfig(label, token, daily_limit, max_chars, enabled)
    return passes


def _today_key() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _read_usage_file() -> dict[str, Any]:
    if not USAGE_PATH.exists():
        return {"date": _today_key(), "passes": {}}
    try:
        payload = json.loads(USAGE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"date": _today_key(), "passes": {}}
    if payload.get("date") != _today_key():
        return {"date": _today_key(), "passes": {}}
    if not isinstance(payload.get("passes"), dict):
        payload["passes"] = {}
    return payload


def _write_usage_file(payload: dict[str, Any]) -> None:
    tmp_path = USAGE_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(USAGE_PATH)


def _get_usage(key: str) -> dict[str, int]:
    with usage_lock:
        payload = _read_usage_file()
        usage = payload["passes"].get(key) or {}
        return {
            "count": int(usage.get("count") or 0),
            "chars": int(usage.get("chars") or 0),
        }


def _increment_usage(key: str, chars: int) -> dict[str, int]:
    with usage_lock:
        payload = _read_usage_file()
        passes = payload["passes"]
        usage = passes.get(key) or {"count": 0, "chars": 0}
        usage["count"] = int(usage.get("count") or 0) + 1
        usage["chars"] = int(usage.get("chars") or 0) + chars
        passes[key] = usage

        global_usage = passes.get("__global__") or {"count": 0, "chars": 0}
        global_usage["count"] = int(global_usage.get("count") or 0) + 1
        global_usage["chars"] = int(global_usage.get("chars") or 0) + chars
        passes["__global__"] = global_usage

        _write_usage_file(payload)
        return {"count": usage["count"], "chars": usage["chars"]}


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]


def _route_path(path: str) -> tuple[str, str]:
    base_path = _load_web_settings().base_path
    if base_path and path == base_path:
        return base_path, "/"
    if base_path and path.startswith(base_path + "/"):
        stripped = path[len(base_path) :]
        return base_path, stripped or "/"
    return "", path


def _normalize_base_path(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.strip()
    if not normalized or normalized == "/":
        return ""
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    return normalized.rstrip("/")


def _env_bool(name: str, default: bool) -> bool:
    from os import getenv

    value = getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    from os import getenv

    return _safe_int(getenv(name), default)


def _safe_int(value: str | None, default: int) -> int:
    try:
        parsed = int(value or "")
    except ValueError:
        return default
    return parsed if parsed > 0 else default


if __name__ == "__main__":
    main()
