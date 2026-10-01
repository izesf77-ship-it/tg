"""Текстовая раскладка: перенос строк, расчёт ширины, работа с emoji."""

from __future__ import annotations

from typing import List, Optional, Sequence

from bot.generators.fonts import FontManager

NO_BREAK_BEFORE = ".,!?;:)]}»›"
NO_BREAK_AFTER = "([{«‹"


def _split_long_word(word: str, max_width: float, fm: FontManager, size: int) -> List[str]:
    """Разрезать слово, которое не помещается в строку (например, длинная ссылка)."""
    parts: List[str] = []
    current = ""
    for ch in word:
        candidate = current + ch
        if current and fm.measure(candidate, size) > max_width:
            parts.append(current)
            current = ch
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def wrap_text(
    text: str,
    fm: FontManager,
    size: int,
    max_width: float,
    max_lines: Optional[int] = None,
    ellipsis: str = "…",
) -> List[str]:
    """Перенос текста по словам с учётом ширины emoji.

    Возвращает список строк. ``max_lines`` ограничивает количество строк,
    последняя при необходимости заканчивается многоточием.
    """
    if not text:
        return []
    lines: List[str] = []
    for hard_line in str(text).split("\n"):
        if not hard_line:
            lines.append("")
            continue
        lines.extend(_wrap_single(hard_line, fm, size, max_width))
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()

    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and fm.measure(last + ellipsis, size) > max_width:
            last = last[:-1]
        lines[-1] = last + ellipsis
    return lines


def _wrap_single(text: str, fm: FontManager, size: int, max_width: float) -> List[str]:
    words = text.split(" ")
    lines: List[str] = []
    current = ""

    for word in words:
        if not word:
            current = current + " " if current else ""
            continue
        if fm.measure(word, size) > max_width:
            if current:
                lines.append(current)
                current = ""
            for part in _split_long_word(word, max_width, fm, size):
                lines.append(part)
            continue

        candidate = f"{current} {word}" if current else word
        if fm.measure(candidate, size) <= max_width:
            current = candidate
            continue

        if current and word and current[-1] in NO_BREAK_AFTER:
            joined = f"{current}{word}"
            if fm.measure(joined, size) <= max_width:
                current = joined
                continue
        if current and word and word[0] in NO_BREAK_BEFORE:
            joined = f"{current}{word}"
            if fm.measure(joined, size) <= max_width:
                current = joined
                continue

        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines


def fit_single_line(
    text: str, fm: FontManager, size: int, max_width: float, ellipsis: str = "…"
) -> str:
    """Обрезать строку до ширины с многоточием."""
    if not text or fm.measure(text, size) <= max_width:
        return text or ""
    cut = text
    while cut and fm.measure(cut + ellipsis, size) > max_width:
        cut = cut[:-1]
    return cut + ellipsis


def block_height(lines: Sequence[str], line_height: int) -> int:
    return int(line_height * max(1, len(lines)))


def widest(lines: Sequence[str], fm: FontManager, size: int) -> float:
    return max((fm.measure(line, size) for line in lines), default=0.0)


__all__ = [
    "wrap_text",
    "fit_single_line",
    "block_height",
    "widest",
    "NO_BREAK_AFTER",
    "NO_BREAK_BEFORE",
]
