from __future__ import annotations

import argparse
import json
import mimetypes
import os
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

from .config import PROJECT_ROOT


SITE_ROOT = PROJECT_ROOT / "site"
MAX_BODY_BYTES = 32 * 1024
COMPLIMENT_OPTIONS = [
    {
        "id": "taste",
        "labels": {
            "zh": "送给作者：你很有品味",
            "en": "For the author: you have excellent taste.",
        },
    },
    {
        "id": "kind",
        "labels": {
            "zh": "送给作者：你真的很用心",
            "en": "For the author: you put real care into this.",
        },
    },
    {
        "id": "lucky",
        "labels": {
            "zh": "送给作者：愿你好人一生平安",
            "en": "For the author: may good things find you.",
        },
    },
    {
        "id": "handsome",
        "labels": {
            "zh": "送给作者：这个工具做得有点帅",
            "en": "For the author: this tool is quietly handsome.",
        },
    },
    {
        "id": "tokens",
        "labels": {
            "zh": "送给作者：谢谢你帮我省 token",
            "en": "For the author: thanks for saving my tokens.",
        },
    },
    {
        "id": "button",
        "labels": {
            "zh": "送给作者：这个按钮值得被点击",
            "en": "For the author: this button deserves the click.",
        },
    },
    {
        "id": "thoughtful",
        "labels": {
            "zh": "送给作者：你想得真周到",
            "en": "For the author: this is thoughtfully made.",
        },
    },
    {
        "id": "prompt",
        "labels": {
            "zh": "送给作者：愿你的 prompt 永远清楚",
            "en": "For the author: may your prompts stay clear.",
        },
    },
    {
        "id": "useful",
        "labels": {
            "zh": "送给作者：KnowSayin 真的有用",
            "en": "For the author: KnowSayin is genuinely useful.",
        },
    },
    {
        "id": "coffee",
        "labels": {
            "zh": "送给作者：请收下一杯精神咖啡",
            "en": "For the author: please accept a virtual coffee.",
        },
    },
]


@dataclass(frozen=True)
class SiteSettings:
    public_url: str
    api_base_url: str
    internal_api_base_url: str
    download_url: str
    github_url: str
    grant_secret: str


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the KnowSayin public website.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8789, type=int)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), KnowSayinSiteHandler)
    print(f"KnowSayin site running at http://{args.host}:{args.port}")
    server.serve_forever()


class KnowSayinSiteHandler(BaseHTTPRequestHandler):
    server_version = "KnowSayinSite/0.1"

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_common_headers("application/json; charset=utf-8")
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path == "/health":
            self._send_json({"ok": True})
            return
        if path == "/api/config":
            self._handle_config()
            return
        if path == "/download":
            self._redirect(_load_settings().download_url)
            return
        if path == "/" or path == "/index.html":
            self._send_index()
            return
        if path.startswith("/static/"):
            self._send_static(path.removeprefix("/static/"))
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path

        if path == "/api/session":
            self._handle_cloud_proxy("/v1/session", require_auth=False)
            return
        if path == "/api/usage":
            self._handle_cloud_proxy("/v1/usage", require_auth=True)
            return
        if path == "/api/clean":
            self._handle_cloud_proxy("/v1/clean", require_auth=True)
            return
        if path == "/api/extra":
            self._handle_extra()
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:
        safe_path = urlparse(self.path).path
        print(f"{self.address_string()} - {self.command} {safe_path} - {format % args}")

    def _handle_config(self) -> None:
        settings = _load_settings()
        self._send_json(
            {
                "publicUrl": settings.public_url,
                "apiBaseUrl": settings.api_base_url,
                "downloadUrl": settings.download_url,
                "githubUrl": settings.github_url,
                "extraEnabled": bool(settings.grant_secret),
                "compliments": COMPLIMENT_OPTIONS,
            }
        )

    def _handle_cloud_proxy(self, internal_path: str, require_auth: bool) -> None:
        payload = self._read_json_body()
        if payload is None:
            return

        headers = {}
        if require_auth:
            token = _bearer_token(self.headers.get("Authorization", ""))
            if not token:
                self._send_json({"error": "BAD_TOKEN", "message": "Session token is required."}, HTTPStatus.UNAUTHORIZED)
                return
            headers["Authorization"] = f"Bearer {token}"

        response, status = _post_internal_json(internal_path, payload, _load_settings(), headers=headers)
        self._send_json(response, status)

    def _handle_extra(self) -> None:
        payload = self._read_json_body()
        if payload is None:
            return

        device_code = _normalize_device_code(str(payload.get("deviceCode") or ""))
        if not device_code:
            self._send_json(
                {
                    "error": "BAD_DEVICE_CODE",
                    "message": "Open this page from the KnowSayin app so your machine code is included.",
                },
                HTTPStatus.BAD_REQUEST,
            )
            return

        compliment_id = str(payload.get("compliment") or "").strip()
        valid_ids = {option["id"] for option in COMPLIMENT_OPTIONS}
        if compliment_id not in valid_ids:
            self._send_json(
                {
                    "error": "BAD_COMPLIMENT",
                    "message": "Pick one nice thing before getting extra quota.",
                },
                HTTPStatus.BAD_REQUEST,
            )
            return

        settings = _load_settings()
        if not settings.grant_secret:
            self._send_json(
                {
                    "error": "EXTRA_NOT_CONFIGURED",
                    "message": "Extra quota is not configured yet.",
                    "deviceCode": device_code,
                },
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return

        response, status = _post_internal_json(
            "/v1/grant",
            {"deviceCode": device_code, "compliment": compliment_id},
            settings,
            headers={"Authorization": f"Bearer {settings.grant_secret}"},
        )
        self._send_json(response, status)

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
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self._send_json({"error": "BAD_JSON"}, HTTPStatus.BAD_REQUEST)
            return None
        if not isinstance(payload, dict):
            self._send_json({"error": "BAD_JSON"}, HTTPStatus.BAD_REQUEST)
            return None
        return payload

    def _send_index(self) -> None:
        self._send_file(SITE_ROOT / "index.html", "text/html; charset=utf-8")

    def _send_static(self, relative: str) -> None:
        safe_parts = [part for part in Path(relative).parts if part not in {"", ".", ".."}]
        if not safe_parts:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        file_path = SITE_ROOT / "static" / Path(*safe_parts)
        if not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        self._send_file(file_path, content_type)

    def _send_file(self, file_path: Path, content_type: str) -> None:
        try:
            body = file_path.read_bytes()
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

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
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")

    def _redirect(self, url: str) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", url)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()


def _load_settings() -> SiteSettings:
    public_url = os.getenv("KNOWSAYIN_SITE_PUBLIC_URL", "https://knowsayin.com").strip()
    github_url = os.getenv("KNOWSAYIN_GITHUB_URL", "https://github.com/aginchan-spec/knowsayin").strip()
    download_url = (
        os.getenv("KNOWSAYIN_SITE_DOWNLOAD_URL")
        or os.getenv("KNOWSAYIN_DOWNLOAD_URL")
        or github_url
    ).strip()
    if _is_self_download_url(download_url, public_url):
        download_url = github_url

    return SiteSettings(
        public_url=public_url,
        api_base_url=os.getenv("KNOWSAYIN_SITE_API_BASE_URL", "https://api.knowsayin.com").strip(),
        internal_api_base_url=os.getenv("KNOWSAYIN_INTERNAL_API_BASE_URL", "http://127.0.0.1:8788").strip(),
        download_url=download_url,
        github_url=github_url,
        grant_secret=os.getenv("KNOWSAYIN_API_GRANT_SECRET", "").strip(),
    )


def _is_self_download_url(download_url: str, public_url: str) -> bool:
    download = urlparse(download_url)
    public = urlparse(public_url)
    return (
        download.scheme in {"http", "https"}
        and download.netloc == public.netloc
        and download.path.rstrip("/") == "/download"
    )


def _post_internal_json(
    internal_path: str,
    payload: dict[str, Any],
    settings: SiteSettings,
    headers: dict[str, str] | None = None,
) -> tuple[dict[str, Any], HTTPStatus]:
    url = f"{settings.internal_api_base_url.rstrip('/')}/{internal_path.lstrip('/')}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        **(headers or {}),
    }
    internal_request = request.Request(
        url,
        data=body,
        method="POST",
        headers=request_headers,
    )

    try:
        with request.urlopen(internal_request, timeout=30) as response:
            response_body = response.read().decode("utf-8")
            return _parse_json_response(response_body), HTTPStatus(response.status)
    except HTTPError as error:
        return _parse_json_response(error.read().decode("utf-8")), HTTPStatus(error.code)
    except URLError:
        return {"error": "INTERNAL_API_UNAVAILABLE"}, HTTPStatus.SERVICE_UNAVAILABLE


def _parse_json_response(value: str) -> dict[str, Any]:
    try:
        payload = json.loads(value)
    except Exception:
        return {"error": "BAD_INTERNAL_RESPONSE"}
    return payload if isinstance(payload, dict) else {"error": "BAD_INTERNAL_RESPONSE"}


def _normalize_device_code(value: str) -> str:
    return "".join(ch for ch in value.upper() if ch.isalnum())[:16]


def _bearer_token(header: str) -> str:
    prefix = "Bearer "
    if not header.startswith(prefix):
        return ""
    return header[len(prefix) :].strip()


if __name__ == "__main__":
    main()
