from __future__ import annotations

import re
from typing import Literal

from openai import OpenAI

from .model_config import DEFAULT_OPTIMIZE_PROMPT, ModelConfig, get_active_model_config


Mode = Literal["light", "medium", "strong"]


FILLER_PATTERNS = [
    r"\b(um+|uh+|er+|ah+|like|you know|i mean)\b",
    r"\b(kind of|sort of)\b",
    r"(嗯+|呃+|啊+|额+|呃呃+|那个|这个|就是|然后|其实|反正|怎么说|你知道吧|对吧)",
]


def optimize_prompt(
    text: str,
    mode: Mode,
    app_settings: ModelConfig | None = None,
) -> str:
    normalized = text.strip()
    if not normalized:
        return ""

    model_config = app_settings or get_active_model_config()

    if not model_config.llm_enabled:
        return fallback_optimize(normalized, mode)

    try:
        return _optimize_with_openai(normalized, mode, model_config)
    except Exception:
        return fallback_optimize(normalized, mode)


def _optimize_with_openai(text: str, mode: Mode, model_config: ModelConfig) -> str:
    client_kwargs: dict[str, str] = {"api_key": model_config.api_key}
    if model_config.base_url:
        client_kwargs["base_url"] = model_config.base_url

    client = OpenAI(**client_kwargs)
    system_prompt = model_config.optimize_prompt.strip() or DEFAULT_OPTIMIZE_PROMPT
    response = client.chat.completions.create(
        model=model_config.model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"请按照系统提示优化以下文本，只输出结果：\n\n{text}",
            },
        ],
    )
    result = response.choices[0].message.content or ""
    return result.strip()


def fallback_optimize(text: str, mode: Mode) -> str:
    cleaned = _remove_fillers(text)
    cleaned = _collapse_repeated_words(cleaned)
    cleaned = _normalize_spacing(cleaned)

    if mode == "light":
        return cleaned

    if mode == "medium":
        return _medium_fallback(cleaned)

    return _strong_fallback(cleaned)


def _remove_fillers(text: str) -> str:
    cleaned = text
    for pattern in FILLER_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"([，。！？、,.!?])\s*\1+", r"\1", cleaned)
    return cleaned


def _collapse_repeated_words(text: str) -> str:
    text = re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"([\u4e00-\u9fff]{1,4})(\s*\1){1,}", r"\1", text)
    return text


def _normalize_spacing(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+([，。！？、,.!?;；:：])", r"\1", text)
    text = re.sub(r"([，。！？、,.!?;；:：])(?=\S)", r"\1 ", text)
    return text.strip()


def _medium_fallback(text: str) -> str:
    if _looks_like_cjk(text):
        return f"请帮我完成以下任务：{text}"
    return f"Please help me with this task: {text}"


def _strong_fallback(text: str) -> str:
    if _looks_like_cjk(text):
        return "\n".join(
            [
                "任务：",
                text,
                "",
                "要求：",
                "- 保留原始意图。",
                "- 输出清楚、简洁、可执行。",
            ]
        )

    return "\n".join(
        [
            "Task:",
            text,
            "",
            "Requirements:",
            "- Preserve the original intent.",
            "- Keep the output clear, concise, and actionable.",
        ]
    )


def _looks_like_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))
