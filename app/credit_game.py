from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class CreditOption:
    value: str
    en: str
    zh: str


@dataclass(frozen=True)
class CreditQuestion:
    id: str
    en: str
    zh: str
    options: tuple[CreditOption, CreditOption]
    correct_answer: str


CREDIT_QUESTIONS: tuple[CreditQuestion, ...] = (
    CreditQuestion(
        id="math_1_plus_1",
        en="1 + 1 = ?",
        zh="1 + 1 = ?",
        options=(CreditOption("2", "2", "2"), CreditOption("3", "3", "3")),
        correct_answer="2",
    ),
    CreditQuestion(
        id="math_2_plus_3",
        en="2 + 3 = ?",
        zh="2 + 3 = ?",
        options=(CreditOption("5", "5", "5"), CreditOption("6", "6", "6")),
        correct_answer="5",
    ),
    CreditQuestion(
        id="math_5_minus_2",
        en="5 - 2 = ?",
        zh="5 - 2 = ?",
        options=(CreditOption("3", "3", "3"), CreditOption("4", "4", "4")),
        correct_answer="3",
    ),
    CreditQuestion(
        id="shortcut_optimize",
        en="Default Optimize shortcut?",
        zh="Optimize 默认快捷键？",
        options=(
            CreditOption("option_shift", "Option + Shift", "Option + Shift"),
            CreditOption("command_q", "Command + Q", "Command + Q"),
        ),
        correct_answer="option_shift",
    ),
    CreditQuestion(
        id="author_good",
        en="Is the author probably a good person?",
        zh="你觉得作者是不是好人？",
        options=(CreditOption("yes", "Yes", "是"), CreditOption("no", "No", "不是")),
        correct_answer="yes",
    ),
    CreditQuestion(
        id="author_care",
        en="Did the author put care into this little app?",
        zh="作者是不是有点用心？",
        options=(CreditOption("yes", "Yes", "是"), CreditOption("no", "No", "不是")),
        correct_answer="yes",
    ),
    CreditQuestion(
        id="kind_click",
        en="Does this button deserve a kind click?",
        zh="这个按钮是不是值得被温柔地点一下？",
        options=(CreditOption("yes", "Yes", "是"), CreditOption("no", "No", "不是")),
        correct_answer="yes",
    ),
)


def random_credit_question() -> CreditQuestion:
    return random.choice(CREDIT_QUESTIONS)


def credit_question_by_id(question_id: str) -> CreditQuestion | None:
    normalized = str(question_id or "").strip()
    for question in CREDIT_QUESTIONS:
        if question.id == normalized:
            return question
    return None


def evaluate_credit_answer(question_id: str, answer: str) -> bool | None:
    question = credit_question_by_id(question_id)
    if question is None:
        return None

    normalized = _normalize_answer(answer)
    valid_answers = {_normalize_answer(option.value) for option in question.options}
    if normalized not in valid_answers:
        return None
    return normalized == _normalize_answer(question.correct_answer)


def _normalize_answer(value: str) -> str:
    return str(value or "").strip().lower().replace(" ", "_")
