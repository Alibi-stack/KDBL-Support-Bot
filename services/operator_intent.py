from __future__ import annotations

import re


OPERATOR_REQUEST_RE = re.compile(
    r"\b("
    r"оператор(?:а|у|ом)?|"
    r"менеджер(?:а|у|ом)?|"
    r"сотрудник(?:а|у|ом)?|"
    r"специалист(?:а|у|ом)?|"
    r"человек(?:а|у|ом)?|"
    r"жив[а-я]*\s+человек|"
    r"поддержк[а-я]*|"
    r"техподдержк[а-я]*|"
    r"подключ[а-я]*|"
    r"позов[а-я]*|"
    r"позвать|"
    r"свяж[а-я]*|"
    r"соедин[а-я]*|"
    r"өтініш|"
    r"оператор(?:ға|ды|мен)?|"
    r"маман(?:ға|ды|мен)?|"
    r"қызметкер(?:ге|ді|мен)?|"
    r"адам(?:ға|ды|мен)?|"
    r"қос(?:ыңыз|у|ып)?|"
    r"шақыр(?:ыңыз|у|ып)?"
    r")\b",
    re.IGNORECASE,
)


def is_operator_request(text: str | None) -> bool:
    if not text:
        return False
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return bool(OPERATOR_REQUEST_RE.search(normalized))


def build_operator_ticket_question(
    current_text: str,
    last_question: str | None,
) -> str:
    if last_question and last_question.strip() and last_question.strip() != current_text.strip():
        return (
            f"Предыдущий вопрос пользователя:\n{last_question.strip()}\n\n"
            f"Пользователь попросил подключить оператора:\n{current_text.strip()}"
        )
    return current_text.strip()
