from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import dotenv_values, set_key

from .config import CONFIG_ROOT


ENV_PATH = CONFIG_ROOT / ".env"
APP_NAME = "KnowSayin"
APP_VERSION = "0.1.0"
CLOUD_PROVIDER_ID = "knowsayin"
DEFAULT_CLOUD_API_BASE_URL = "https://api.knowsayin.com"
DEFAULT_CLOUD_MODEL = "knowsayin-cloud"
DEFAULT_OPTIMIZE_HOTKEY = "option+shift"
DEFAULT_UNDO_HOTKEY = "option*3"
DEFAULT_LANG1_CODE = "zh"
DEFAULT_LANG1_HOTKEY = "option+1"
DEFAULT_LANG2_CODE = "en"
DEFAULT_LANG2_HOTKEY = "option+2"

DEFAULT_OPTIMIZE_PROMPT = """You are a voice-to-prompt cleanup assistant.

Task: Rewrite the user's rough spoken, dictated, or stream-of-consciousness text into a clear prompt that is ready to send to an AI assistant.

Rules:
1. Remove meaningless filler words, pauses, false starts, and repeated phrases.
2. Handle self-corrections correctly, using the user's final intended meaning.
3. Do not add requirements, facts, constraints, or goals that the user did not express.
4. Preserve the task goal, important constraints, tone, and requested output format.
5. If the user's wording is messy, organize it into a clearer structure without making extra decisions for them.
6. Output only the cleaned prompt. Do not explain your changes."""


@dataclass(frozen=True)
class ModelConfig:
    provider_id: str
    provider_name: str
    base_url: str
    model: str
    api_key: str
    optimize_prompt: str
    disable_llm: bool = False

    @property
    def is_cloud(self) -> bool:
        return self.provider_id == CLOUD_PROVIDER_ID

    @property
    def api_key_configured(self) -> bool:
        return bool(self.api_key.strip())

    @property
    def llm_enabled(self) -> bool:
        return self.is_cloud and bool(self.base_url.strip()) and not self.disable_llm


def load_model_settings() -> dict[str, str]:
    values = _read_env()
    return {
        "provider_id": CLOUD_PROVIDER_ID,
        "base_url": DEFAULT_CLOUD_API_BASE_URL,
        "model": DEFAULT_CLOUD_MODEL,
        "api_key": "",
        "optimize_prompt": DEFAULT_OPTIMIZE_PROMPT,
        "optimize_hotkey": values.get("KNOWSAYIN_OPTIMIZE_HOTKEY") or DEFAULT_OPTIMIZE_HOTKEY,
        "undo_hotkey": values.get("KNOWSAYIN_UNDO_HOTKEY") or DEFAULT_UNDO_HOTKEY,
        "lang1_code": values.get("KNOWSAYIN_LANG1_CODE") or DEFAULT_LANG1_CODE,
        "lang1_hotkey": values.get("KNOWSAYIN_LANG1_HOTKEY") or DEFAULT_LANG1_HOTKEY,
        "lang2_code": values.get("KNOWSAYIN_LANG2_CODE") or DEFAULT_LANG2_CODE,
        "lang2_hotkey": values.get("KNOWSAYIN_LANG2_HOTKEY") or DEFAULT_LANG2_HOTKEY,
    }


def save_desktop_settings(
    optimize_hotkey: str = DEFAULT_OPTIMIZE_HOTKEY,
    undo_hotkey: str = DEFAULT_UNDO_HOTKEY,
    lang1_code: str = DEFAULT_LANG1_CODE,
    lang1_hotkey: str = DEFAULT_LANG1_HOTKEY,
    lang2_code: str = DEFAULT_LANG2_CODE,
    lang2_hotkey: str = DEFAULT_LANG2_HOTKEY,
) -> None:
    _ensure_env_file()
    _set_env("KNOWSAYIN_PROVIDER", CLOUD_PROVIDER_ID)
    _set_env("KNOWSAYIN_CLOUD_BASE_URL", DEFAULT_CLOUD_API_BASE_URL)
    _set_env("KNOWSAYIN_CLOUD_MODEL", DEFAULT_CLOUD_MODEL)
    _set_env("KNOWSAYIN_OPTIMIZE_HOTKEY", optimize_hotkey.strip() or DEFAULT_OPTIMIZE_HOTKEY)
    _set_env("KNOWSAYIN_UNDO_HOTKEY", undo_hotkey.strip() or DEFAULT_UNDO_HOTKEY)
    _set_env("KNOWSAYIN_LANG1_CODE", lang1_code.strip() or DEFAULT_LANG1_CODE)
    _set_env("KNOWSAYIN_LANG1_HOTKEY", lang1_hotkey.strip() or DEFAULT_LANG1_HOTKEY)
    _set_env("KNOWSAYIN_LANG2_CODE", lang2_code.strip() or DEFAULT_LANG2_CODE)
    _set_env("KNOWSAYIN_LANG2_HOTKEY", lang2_hotkey.strip() or DEFAULT_LANG2_HOTKEY)
    os.chmod(ENV_PATH, 0o600)


def get_active_model_config() -> ModelConfig:
    data = load_model_settings()
    return ModelConfig(
        provider_id=CLOUD_PROVIDER_ID,
        provider_name="KnowSayin Cloud",
        base_url=DEFAULT_CLOUD_API_BASE_URL,
        model=DEFAULT_CLOUD_MODEL,
        api_key="",
        optimize_prompt=DEFAULT_OPTIMIZE_PROMPT,
        disable_llm=False,
    )


def _read_env() -> dict[str, str]:
    values = {key: value or "" for key, value in dotenv_values(ENV_PATH).items()}
    for key in (
        "KNOWSAYIN_CLOUD_TOKEN",
        "KNOWSAYIN_OPTIMIZE_HOTKEY",
        "KNOWSAYIN_UNDO_HOTKEY",
        "KNOWSAYIN_LANG1_CODE",
        "KNOWSAYIN_LANG1_HOTKEY",
        "KNOWSAYIN_LANG2_CODE",
        "KNOWSAYIN_LANG2_HOTKEY",
    ):
        if os.getenv(key):
            values[key] = os.getenv(key, "")
    return values


def _ensure_env_file() -> None:
    if ENV_PATH.exists():
        return
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    ENV_PATH.write_text(
        "# Local KnowSayin config. Do not commit this file.\n",
        encoding="utf-8",
    )


def _set_env(key: str, value: str) -> None:
    set_key(str(ENV_PATH), key, value, quote_mode="always")


def _encode_env_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")


def _decode_env_text(value: str) -> str:
    return value.replace("\\n", "\n")


def _env_bool(name: str, default: bool = False) -> bool:
    value = _read_env().get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_cloud_session_token() -> str:
    return _read_env().get("KNOWSAYIN_CLOUD_TOKEN", "").strip()


def save_cloud_session_token(token: str) -> None:
    _ensure_env_file()
    _set_env("KNOWSAYIN_CLOUD_TOKEN", token.strip())
    os.chmod(ENV_PATH, 0o600)
