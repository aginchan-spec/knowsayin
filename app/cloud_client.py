from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Literal

from .model_config import (
    APP_NAME,
    APP_VERSION,
    DEFAULT_CLOUD_API_BASE_URL,
    load_cloud_session_token,
    save_cloud_session_token,
)


Mode = Literal["light", "medium", "strong"]
REQUEST_TIMEOUT_SECONDS = 30


@dataclass
class CloudAPIError(RuntimeError):
    code: str
    message: str
    status: int = 0

    def __str__(self) -> str:
        return self.message or self.code


def clean_prompt_with_cloud(text: str, mode: Mode, base_url: str = DEFAULT_CLOUD_API_BASE_URL) -> str:
    token = load_cloud_session_token() or create_session(base_url)["token"]
    try:
        return _clean_with_token(text, mode, base_url, token)
    except CloudAPIError as exc:
        if exc.status not in {401, 403}:
            raise
        save_cloud_session_token("")
        token = create_session(base_url)["token"]
        return _clean_with_token(text, mode, base_url, token)


def get_cloud_config(base_url: str = DEFAULT_CLOUD_API_BASE_URL) -> dict[str, Any]:
    return _request_json("GET", "/v1/config", None, base_url)


def create_session(base_url: str = DEFAULT_CLOUD_API_BASE_URL) -> dict[str, Any]:
    payload = _request_json("POST", "/v1/session", {}, base_url)
    token = str(payload.get("token") or "").strip()
    if not token:
        raise CloudAPIError("BAD_SESSION", "云端没有返回可用 session。", 502)
    save_cloud_session_token(token)
    return payload


def _clean_with_token(text: str, mode: Mode, base_url: str, token: str) -> str:
    payload = _request_json(
        "POST",
        "/v1/clean",
        {"text": text, "mode": mode},
        base_url,
        token=token,
    )
    result = str(payload.get("result") or "").strip()
    if not result:
        raise CloudAPIError("EMPTY_RESULT", "云端返回了空结果。", 502)
    return result


def _request_json(
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    base_url: str,
    token: str | None = None,
) -> dict[str, Any]:
    url = _join_url(base_url, path)
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "User-Agent": f"{APP_NAME}/{APP_VERSION}",
    }
    if body is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return _decode_json(response.read())
    except urllib.error.HTTPError as exc:
        payload = _decode_json(exc.read())
        raise CloudAPIError(
            str(payload.get("error") or "HTTP_ERROR"),
            str(payload.get("message") or f"云端请求失败（HTTP {exc.code}）。"),
            exc.code,
        ) from exc
    except urllib.error.URLError as exc:
        raise CloudAPIError("NETWORK_ERROR", f"无法连接 KnowSayin Cloud：{exc.reason}", 0) from exc
    except TimeoutError as exc:
        raise CloudAPIError("TIMEOUT", "连接 KnowSayin Cloud 超时。", 0) from exc


def _decode_json(body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _join_url(base_url: str, path: str) -> str:
    normalized = (base_url or DEFAULT_CLOUD_API_BASE_URL).strip().rstrip("/")
    if not normalized.startswith(("https://", "http://")):
        normalized = DEFAULT_CLOUD_API_BASE_URL
    return normalized + "/" + path.lstrip("/")
