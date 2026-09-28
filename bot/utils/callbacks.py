"""Парсер callback_data.

Формат: ``screen:action:arg1:arg2`` (максимум 64 байта в Telegram).
Первое значение — экран, второе — действие, остальные — аргументы.
"""

from __future__ import annotations

from typing import Any, List, Sequence

SEP = ":"
MAX_LEN = 64

# Экраны
S_MENU = "mn"
S_STYLE = "st"
S_PART = "pp"
S_EDIT = "ed"
S_MSG = "ms"
S_MY = "my"
S_SETTINGS = "se"
S_AI = "ai"
S_TPL = "tpl"
S_ADMIN = "ad"


def cb(*parts: Any) -> str:
    """Собрать callback_data из частей (None/'' отбрасываются)."""
    chunks: List[str] = []
    for p in parts:
        if p is None or p == "":
            continue
        chunks.append(str(p).replace(SEP, "-").replace(" ", "_"))
    data = SEP.join(chunks)
    if len(data.encode("utf-8")) > MAX_LEN:  # pragma: no cover - защита
        raise ValueError(f"callback_data слишком длинный: {data}")
    return data


def parse(data: str) -> List[str]:
    if not data:
        return []
    return data.split(SEP)


def head(data: str) -> str:
    parts = parse(data)
    return parts[0] if parts else ""


def action(data: str) -> str:
    parts = parse(data)
    return parts[1] if len(parts) > 1 else ""


def arg(data: str, index: int, default: str = "") -> str:
    """Аргумент после ``screen`` и ``action`` (индекс 0 = первый)."""
    parts = parse(data)
    pos = index + 2
    return parts[pos] if len(parts) > pos else default


def arg_int(data: str, index: int, default: int = -1) -> int:
    raw = arg(data, index)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def chat_id_of(data: str, default: int = -1) -> int:
    """ID переписки из callback_data — всегда ПОСЛЕДНИЙ аргумент.

    Раньше в хендлерах бралась фиксированная позиция (``arg_int(data, 2)``),
    но у разных кнопок ``chat_id`` стоял на разном месте: у ``pp:open:0:7``
    это индекс 1, а у ``pp:next:7`` — индекс 0. Из-за этого почти все
    кнопки отвечали «Переписка не найдена».
    """
    parts = parse(data)
    if len(parts) < 2:
        return default
    try:
        return int(parts[-1])
    except (TypeError, ValueError):
        return default


# Варианты пометки на изображении.
# Ключ NONE означает «без пометки» (пустая строка) — так выключают её.
DISCLAIMERS = {
    "NONE": "",
    "FICTIONAL": "FICTIONAL CHAT",
    "ВЫМЫШЛЕННАЯ": "ВЫМЫШЛЕННАЯ ПЕРЕПИСКА",
    "FICTIONAL_CHAT_ВЫМЫШЛЕННАЯ_ПЕРЕПИСКА": "FICTIONAL CHAT · ВЫМЫШЛЕННАЯ ПЕРЕПИСКА",
}


__all__ = [
    "SEP",
    "MAX_LEN",
    "DISCLAIMERS",
    "cb",
    "parse",
    "head",
    "action",
    "arg",
    "arg_int",
    "chat_id_of",
    "S_MENU",
    "S_STYLE",
    "S_PART",
    "S_EDIT",
    "S_MSG",
    "S_MY",
    "S_SETTINGS",
    "S_AI",
    "S_TPL",
    "S_ADMIN",
]
