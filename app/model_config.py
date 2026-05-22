from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any

from dotenv import dotenv_values, set_key

from .config import PROJECT_ROOT


ENV_PATH = PROJECT_ROOT / ".env"
DEFAULT_OPTIMIZE_HOTKEY = "option+shift"
DEFAULT_UNDO_HOTKEY = "option*3"

DEFAULT_OPTIMIZE_PROMPT = """你是一个语音提示词清洗助手。

任务：把用户口语化、思考流、语音输入转写出来的文本，整理成更适合发送给 AI 的清楚 prompt。

规则：
1. 删除无意义口头禅、停顿词、重复词。
2. 正确处理用户自我纠正，以最后确认的意思为准。
3. 不要添加用户没有表达过的新需求。
4. 保留任务目标、限制条件、语气、格式要求。
5. 如果用户表达混乱，请整理结构，但不要替用户做额外决策。
6. 输出只包含整理后的 prompt，不要解释。"""


@dataclass(frozen=True)
class ProviderPreset:
    provider_id: str
    name: str
    base_url: str
    default_model: str


PROVIDER_PRESETS: tuple[ProviderPreset, ...] = (
    ProviderPreset("openai", "OpenAI", "https://api.openai.com/v1", "gpt-4.1-nano"),
    ProviderPreset("openrouter", "OpenRouter", "https://openrouter.ai/api/v1", "openai/gpt-4.1-nano"),
    ProviderPreset("deepseek", "DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat"),
    ProviderPreset("groq", "Groq", "https://api.groq.com/openai/v1", "llama-3.1-8b-instant"),
    ProviderPreset("mistral", "Mistral", "https://api.mistral.ai/v1", "mistral-small-latest"),
    ProviderPreset("together", "Together AI", "https://api.together.xyz/v1", "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
    ProviderPreset("xai", "xAI", "https://api.x.ai/v1", "grok-3-mini"),
    ProviderPreset("moonshot", "Moonshot", "https://api.moonshot.ai/v1", "moonshot-v1-8k"),
    ProviderPreset("qwen", "Qwen / DashScope", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-turbo"),
    ProviderPreset("doubao", "Doubao / Volcano Ark", "https://ark.cn-beijing.volces.com/api/v3", ""),
    ProviderPreset("custom", "Custom OpenAI-compatible", "", ""),
)


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
    def api_key_configured(self) -> bool:
        return bool(self.api_key.strip())

    @property
    def llm_enabled(self) -> bool:
        return self.api_key_configured and bool(self.model.strip()) and not self.disable_llm


def provider_names() -> list[str]:
    return [preset.name for preset in PROVIDER_PRESETS]


def provider_by_id(provider_id: str) -> ProviderPreset:
    for preset in PROVID_PRESETS_SAFE():
        if preset.provider_id == provider_id:
            return preset
    return PROVIDER_PRESETS[0]


def provider_by_name(name: str) -> ProviderPreset:
    for preset in PROVID_PRESETS_SAFE():
        if preset.name == name:
            return preset
    return PROVIDER_PRESETS[0]


def load_model_settings() -> dict[str, str]:
    values = _read_env()
    provider_id = values.get("JUSTSAYING_PROVIDER") or "openai"
    provider = provider_by_id(provider_id)
    return {
        "provider_id": provider.provider_id,
        "base_url": values.get("OPENAI_BASE_URL") or provider.base_url,
        "model": values.get("OPENAI_MODEL") or provider.default_model,
        "api_key": values.get("OPENAI_API_KEY") or "",
        "optimize_prompt": _decode_env_text(
            values.get("JUSTSAYING_OPTIMIZE_PROMPT") or DEFAULT_OPTIMIZE_PROMPT,
        ),
        "optimize_hotkey": values.get("JUSTSAYING_OPTIMIZE_HOTKEY") or DEFAULT_OPTIMIZE_HOTKEY,
        "undo_hotkey": values.get("JUSTSAYING_UNDO_HOTKEY") or DEFAULT_UNDO_HOTKEY,
    }


def save_model_settings(
    provider_id: str,
    base_url: str,
    model: str,
    api_key: str,
    optimize_prompt: str,
    optimize_hotkey: str = DEFAULT_OPTIMIZE_HOTKEY,
    undo_hotkey: str = DEFAULT_UNDO_HOTKEY,
) -> None:
    _ensure_env_file()
    _set_env("JUSTSAYING_PROVIDER", provider_id)
    _set_env("OPENAI_BASE_URL", base_url.strip())
    _set_env("OPENAI_MODEL", model.strip())
    _set_env("OPENAI_API_KEY", api_key.strip())
    _set_env(
        "JUSTSAYING_OPTIMIZE_PROMPT",
        _encode_env_text(optimize_prompt.strip() or DEFAULT_OPTIMIZE_PROMPT),
    )
    _set_env("JUSTSAYING_OPTIMIZE_HOTKEY", optimize_hotkey.strip() or DEFAULT_OPTIMIZE_HOTKEY)
    _set_env("JUSTSAYING_UNDO_HOTKEY", undo_hotkey.strip() or DEFAULT_UNDO_HOTKEY)
    os.chmod(ENV_PATH, 0o600)


def get_active_model_config() -> ModelConfig:
    data = load_model_settings()
    provider = provider_by_id(data["provider_id"])

    return ModelConfig(
        provider_id=provider.provider_id,
        provider_name=provider.name,
        base_url=data["base_url"].strip(),
        model=data["model"].strip(),
        api_key=data["api_key"].strip(),
        optimize_prompt=data["optimize_prompt"].strip() or DEFAULT_OPTIMIZE_PROMPT,
        disable_llm=_env_bool("JUSTSAYING_DISABLE_LLM", False),
    )


def load_api_key(provider_id: str | None = None) -> str:
    return load_model_settings().get("api_key", "")


def list_remote_models(base_url: str, api_key: str) -> list[str]:
    if not base_url.strip():
        raise RuntimeError("请先填写 Base URL。")
    if not api_key.strip():
        raise RuntimeError("请先填写 API key。")

    url = base_url.rstrip("/") + "/models"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key.strip()}",
            "Accept": "application/json",
            "User-Agent": "JustSaying/0.1",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"模型列表读取失败：{exc}") from exc

    model_ids = _extract_model_ids(payload)
    if not model_ids:
        raise RuntimeError("没有从接口返回中找到模型 ID。")
    return model_ids


def _extract_model_ids(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            values = [
                str(item.get("id"))
                for item in data
                if isinstance(item, dict) and item.get("id")
            ]
            return sorted(set(values), key=str.lower)

        models = payload.get("models")
        if isinstance(models, list):
            values = [
                str(item.get("id") or item.get("name"))
                for item in models
                if isinstance(item, dict) and (item.get("id") or item.get("name"))
            ]
            return sorted(set(values), key=str.lower)

    return []


def _read_env() -> dict[str, str]:
    values = {key: value or "" for key, value in dotenv_values(ENV_PATH).items()}
    for key in (
        "JUSTSAYING_PROVIDER",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "JUSTSAYING_OPTIMIZE_PROMPT",
        "JUSTSAYING_OPTIMIZE_HOTKEY",
        "JUSTSAYING_UNDO_HOTKEY",
        "JUSTSAYING_DISABLE_LLM",
    ):
        if os.getenv(key):
            values[key] = os.getenv(key, "")
    return values


def _ensure_env_file() -> None:
    if ENV_PATH.exists():
        return
    ENV_PATH.write_text(
        "# Local Just Saying config. Do not commit this file.\n",
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


def PROVID_PRESETS_SAFE() -> tuple[ProviderPreset, ...]:
    return PROVIDER_PRESETS
