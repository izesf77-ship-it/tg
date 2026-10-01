"""Работа с пользовательским текстом: обрезка, экранирование, склонения."""

from __future__ import annotations

import html
import re
from typing import Iterable

WHITESPACE_RE = re.compile(r"\s+")
MAX_MESSAGE_LENGTH = 4096
MAX_NAME_LENGTH = 64
MAX_USERNAME_LENGTH = 32
MAX_STATUS_LENGTH = 64
MAX_CAPTION_LENGTH = 1024

VOWELS = ("а", "е", "ё", "и", "о", "у", "ы", "э", "ю", "я")


def clean(text: str) -> str:
    """Схлопнуть пробелы и обрезать края."""
    if not text:
        return ""
    return WHITESPACE_RE.sub(" ", str(text)).strip()


def clamp(text: str, limit: int) -> str:
    text = clean(text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def clean_multiline(text: str) -> str:
    """Normalize whitespace without collapsing paragraph breaks."""
    if not text:
        return ""
    normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [WHITESPACE_RE.sub(" ", line).strip() for line in normalized.split("\n")]
    return "\n".join(lines).strip("\n")


def clamp_multiline(text: str, limit: int) -> str:
    text = clean_multiline(text)
    if len(text) <= limit:
        return text
    if limit <= 0:
        return ""
    return text[: limit - 1].rstrip() + "…"


def esc(text: str) -> str:
    """Экранирование для HTML parse_mode."""
    return html.escape(str(text or ""), quote=False)


def plural_ru(number: int, one: str, few: str, many: str) -> str:
    """Склонение числительных: 1 сообщение / 2 сообщения / 5 сообщений."""
    n = abs(int(number))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def messages_word(number: int) -> str:
    return f"{number} {plural_ru(number, 'сообщение', 'сообщения', 'сообщений')}"


def participants_word(number: int) -> str:
    return f"{number} {plural_ru(number, 'участник', 'участника', 'участников')}"


def truncate_preview(text: str, limit: int = 60) -> str:
    text = clean(text).replace("\n", " ")
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def ensure_username(raw: str) -> str:
    """Нормализует @username (без @, только latin/цифры/_)."""
    value = clean(raw).lstrip("@").strip()
    value = re.sub(r"[^A-Za-z0-9_]", "", value)
    return value[:MAX_USERNAME_LENGTH]


def join_lines(lines: Iterable[str]) -> str:
    return "\n".join(str(x) for x in lines if x is not None)


def first_letter(name: str, default: str = "?") -> str:
    name = clean(name)
    return name[0].upper() if name else default


def fit_text(text: str, limit: int) -> str:
    return clamp(text, limit)


__all__ = [
    "clean",
    "clamp",
    "clean_multiline",
    "clamp_multiline",
    "esc",
    "plural_ru",
    "messages_word",
    "participants_word",
    "truncate_preview",
    "ensure_username",
    "join_lines",
    "first_letter",
    "fit_text",
    "MAX_MESSAGE_LENGTH",
    "MAX_NAME_LENGTH",
    "MAX_USERNAME_LENGTH",
    "MAX_STATUS_LENGTH",
    "MAX_CAPTION_LENGTH",
]
