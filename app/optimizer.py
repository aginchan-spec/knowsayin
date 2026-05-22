from __future__ import annotations

import re
from typing import Literal

from openai import OpenAI

from .cloud_client import clean_prompt_with_cloud
from .model_config import DEFAULT_OPTIMIZE_PROMPT, ModelConfig, get_active_model_config


Mode = Literal["light", "medium", "strong"]
LONG_TEXT_THRESHOLD = 800


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

    if model_config.is_cloud and model_config.llm_enabled:
        return clean_prompt_with_cloud(normalized, mode, model_config.base_url)

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
            {"role": "user", "content": _optimize_user_message(text, mode)},
        ],
    )
    result = response.choices[0].message.content or ""
    return result.strip()


def _optimize_user_message(text: str, mode: Mode) -> str:
    if len(text) < LONG_TEXT_THRESHOLD:
        return f"请按照系统提示优化以下文本，只输出结果：\n\n{text}"

    return "\n".join(
        [
            "这是一段较长、可能包含口语化思路流的文本。",
            "请先在内部识别用户真正想完成的任务、背景、限制、关键细节和输出期待。",
            "然后只输出一个可以直接复制使用的清晰 prompt。",
            "不要输出分析过程、摘要标题或多版本选项。",
            f"整理模式：{mode}",
            "",
            text,
        ]
    )


def fallback_optimize(text: str, mode: Mode) -> str:
    cleaned = _remove_fillers(text)
    cleaned = _collapse_repeated_words(cleaned)
    cleaned = _normalize_spacing(cleaned)

    if len(cleaned) >= LONG_TEXT_THRESHOLD and mode != "light":
        return _long_text_fallback(cleaned)

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


def _long_text_fallback(text: str) -> str:
    if _looks_like_cjk(text):
        return "\n".join(
            [
                "请基于以下材料帮我完成任务。",
                "",
                "材料：",
                text,
                "",
                "要求：",
                "- 先理解我的核心意图。",
                "- 保留重要背景和限制。",
                "- 输出清晰、结构化、可直接执行。",
            ]
        )

    return "\n".join(
        [
            "Please help me complete the task based on the material below.",
            "",
            "Material:",
            text,
            "",
            "Requirements:",
            "- Identify my core intent.",
            "- Preserve important context and constraints.",
            "- Produce a clear, structured, directly usable result.",
        ]
    )


def _looks_like_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))
