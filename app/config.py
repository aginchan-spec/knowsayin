from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(
    os.getenv("JUSTSAYING_PROJECT_ROOT") or Path(__file__).resolve().parents[1],
)
APP_SUPPORT_ROOT = Path.home() / "Library" / "Application Support" / "KnowSayin"
OLD_APP_SUPPORT_ROOT = Path.home() / "Library" / "Application Support" / "Just Saying"
CONFIG_ROOT = Path(
    os.getenv("KNOWSAYIN_CONFIG_ROOT")
    or os.getenv("JUSTSAYING_CONFIG_ROOT")
    or (APP_SUPPORT_ROOT if getattr(sys, "frozen", False) else PROJECT_ROOT),
)

if CONFIG_ROOT == APP_SUPPORT_ROOT and not (CONFIG_ROOT / ".env").exists():
    old_env = OLD_APP_SUPPORT_ROOT / ".env"
    if old_env.exists():
        CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_env, CONFIG_ROOT / ".env")
        os.chmod(CONFIG_ROOT / ".env", 0o600)

load_dotenv(CONFIG_ROOT / ".env")


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
