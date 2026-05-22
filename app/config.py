from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_base_url: str | None = os.getenv("OPENAI_BASE_URL")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-nano")
    disable_llm: bool = _env_bool("JUSTSAYING_DISABLE_LLM", False)

    @property
    def api_key_configured(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def llm_enabled(self) -> bool:
        return self.api_key_configured and not self.disable_llm


settings = Settings()
