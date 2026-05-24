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


CREDIT_GAME_DELTA = 5


CREDIT_QUESTIONS: tuple[CreditQuestion, ...] = (
    CreditQuestion(
        id="math_1_plus_1",
        en="1 + 1 = ?",
        zh="1 + 1 = ?",
        options=(CreditOption("2", "2", "2"), CreditOption("3", "3", "3")),
        correct_answer="2",
    ),
    CreditQuestion(
        id="math_2_plus_2",
        en="2 + 2 = ?",
        zh="2 + 2 = ?",
        options=(CreditOption("4", "4", "4"), CreditOption("9", "9", "9")),
        correct_answer="4",
    ),
    CreditQuestion(
        id="math_5_bigger_than_2",
        en="Which number is bigger?",
        zh="哪个数字更大？",
        options=(CreditOption("5", "5", "5"), CreditOption("2", "2", "2")),
        correct_answer="5",
    ),
    CreditQuestion(
        id="week_days",
        en="How many days are in a week?",
        zh="一周有几天？",
        options=(CreditOption("7", "7", "7"), CreditOption("3", "3", "3")),
        correct_answer="7",
    ),
    CreditQuestion(
        id="sun_day",
        en="The sun is bright in the...",
        zh="太阳通常白天会...",
        options=(
            CreditOption("day", "Day", "亮"),
            CreditOption("pocket", "Pocket", "装进口袋"),
        ),
        correct_answer="day",
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
        en="Did the author try a little bit?",
        zh="作者是不是有一点点用心？",
        options=(CreditOption("yes", "Yes", "是"), CreditOption("no", "No", "不是")),
        correct_answer="yes",
    ),
    CreditQuestion(
        id="kind_click",
        en="Does this button deserve a nice click?",
        zh="这个按钮是不是值得被点一下？",
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
