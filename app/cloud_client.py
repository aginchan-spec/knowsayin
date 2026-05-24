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
    payload: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.message or self.code


def clean_prompt_with_cloud(
    text: str,
    mode: Mode,
    base_url: str = DEFAULT_CLOUD_API_BASE_URL,
    target_lang: str | None = None,
) -> str:
    token = load_cloud_session_token() or create_session(base_url)["token"]
    try:
        return _clean_with_token(text, mode, base_url, token, target_lang=target_lang)
    except CloudAPIError as exc:
        if exc.status not in {401, 403}:
            raise
        save_cloud_session_token("")
        token = create_session(base_url)["token"]
        return _clean_with_token(text, mode, base_url, token, target_lang=target_lang)


def get_cloud_usage(base_url: str = DEFAULT_CLOUD_API_BASE_URL) -> dict[str, Any]:
    token = load_cloud_session_token() or create_session(base_url)["token"]
    try:
        return _usage_with_token(base_url, token)
    except CloudAPIError as exc:
        if exc.status not in {401, 403}:
            raise
        save_cloud_session_token("")
        token = create_session(base_url)["token"]
        return _usage_with_token(base_url, token)


def submit_credit_game(
    question_id: str,
    answer: str,
    base_url: str = DEFAULT_CLOUD_API_BASE_URL,
) -> dict[str, Any]:
    token = load_cloud_session_token() or create_session(base_url)["token"]
    try:
        return _credit_game_with_token(base_url, token, question_id, answer)
    except CloudAPIError as exc:
        if exc.status not in {401, 403}:
            raise
        save_cloud_session_token("")
        token = create_session(base_url)["token"]
        return _credit_game_with_token(base_url, token, question_id, answer)


def get_cloud_config(base_url: str = DEFAULT_CLOUD_API_BASE_URL) -> dict[str, Any]:
    return _request_json("GET", "/v1/config", None, base_url)


def create_session(base_url: str = DEFAULT_CLOUD_API_BASE_URL) -> dict[str, Any]:
    payload = _request_json("POST", "/v1/session", {}, base_url)
    token = str(payload.get("token") or "").strip()
    if not token:
        raise CloudAPIError("BAD_SESSION", "Cloud did not return a usable session.", 502)
    save_cloud_session_token(token)
    return payload


def _usage_with_token(base_url: str, token: str) -> dict[str, Any]:
    return _request_json("POST", "/v1/usage", {}, base_url, token=token)


def _clean_with_token(
    text: str,
    mode: Mode,
    base_url: str,
    token: str,
    target_lang: str | None = None,
) -> str:
    body = {"text": text, "mode": mode}
    if target_lang:
        body["targetLang"] = target_lang

    payload = _request_json(
        "POST",
        "/v1/clean",
        body,
        base_url,
        token=token,
    )
    result = str(payload.get("result") or "").strip()
    if not result:
        raise CloudAPIError("EMPTY_RESULT", "Cloud returned an empty result.", 502)
    return result


def _credit_game_with_token(base_url: str, token: str, question_id: str, answer: str) -> dict[str, Any]:
    return _request_json(
        "POST",
        "/v1/credit-game",
        {"questionId": question_id, "answer": answer},
        base_url,
        token=token,
    )


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
        code = str(payload.get("error") or "HTTP_ERROR")
        raise CloudAPIError(
            code,
            _cloud_error_message(code, exc.code),
            exc.code,
            payload,
        ) from exc
    except urllib.error.URLError as exc:
        raise CloudAPIError("NETWORK_ERROR", f"Cannot reach KnowSayin Cloud: {exc.reason}", 0) from exc
    except TimeoutError as exc:
        raise CloudAPIError("TIMEOUT", "KnowSayin Cloud timed out.", 0) from exc


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


def _cloud_error_message(code: str, status: int) -> str:
    messages = {
        "EMPTY_TEXT": "Enter text to optimize.",
        "TEXT_TOO_LONG": "This text is too long for one request.",
        "DAILY_LIMIT": "Today's free quota is used up.",
        "QUOTA_EMPTY": "Free quota is empty. Click Get extra or wait for it to refill.",
        "RATE_LIMITED": "Too many requests. Please try again shortly.",
        "GLOBAL_LIMIT": "Today's shared cloud quota is used up.",
        "UPSTREAM_FAILED": "Cloud optimization failed. Please try again later.",
        "BAD_TOKEN": "Cloud session expired. Please try again.",
        "EMPTY_BODY": "The cloud request was empty.",
        "BODY_TOO_LARGE": "The cloud request was too large.",
        "BAD_JSON": "The cloud request was invalid.",
        "BAD_CREDIT_QUESTION": "That credit question is no longer available.",
        "BAD_CREDIT_ANSWER": "That credit answer was not recognized.",
        "CREDIT_GAME_COOLDOWN": "Quick credit is cooling down.",
    }
    return messages.get(code, f"Cloud request failed (HTTP {status}).")
