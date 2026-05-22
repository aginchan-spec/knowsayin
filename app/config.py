from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(
    os.getenv("KNOWSAYIN_PROJECT_ROOT") or Path(__file__).resolve().parents[1],
)
APP_SUPPORT_ROOT = Path.home() / "Library" / "Application Support" / "KnowSayin"
CONFIG_ROOT = Path(
    os.getenv("KNOWSAYIN_CONFIG_ROOT")
    or (APP_SUPPORT_ROOT if getattr(sys, "frozen", False) else PROJECT_ROOT),
)

load_dotenv(CONFIG_ROOT / ".env")


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    cloud_base_url: str = os.getenv("KNOWSAYIN_CLOUD_BASE_URL", "https://api.knowsayin.com")

    @property
    def api_key_configured(self) -> bool:
        return False

    @property
    def llm_enabled(self) -> bool:
        return True


settings = Settings()
