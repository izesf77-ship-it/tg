"""Работа с временем: разбор пользовательского ввода и форматирование дат."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from bot.utils.errors import InvalidTimeError

_TIME_RE = re.compile(r"^(\d{1,2})\s*[:.\-]?\s*(\d{2})$")

RU_MONTHS_GEN = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)
RU_MONTHS_SHORT = (
    "янв", "фев", "мар", "апр", "мая", "июн",
    "июл", "авг", "сен", "окт", "ноя", "дек",
)
RU_WEEKDAYS = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")


def now_local() -> datetime:
    return datetime.now()


def current_time_str() -> str:
    """Текущее время в формате HH:MM."""
    return now_local().strftime("%H:%M")


def parse_time(raw: str) -> str:
    """Нормализовать пользовательский ввод времени к 'HH:MM'.

    Поддерживает: ``12:41``, ``9:05``, ``2307``, ``9.15``, ``9-15``.
    Бросает :class:`InvalidTimeError` при некорректном вводе.
    """
    if raw is None:
        raise InvalidTimeError()
    text = str(raw).strip().replace(" ", "")
    if not text:
        raise InvalidTimeError()
    match = _TIME_RE.match(text)
    if not match:
        raise InvalidTimeError()
    hours, minutes = int(match.group(1)), int(match.group(2))
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        raise InvalidTimeError()
    return f"{hours:02d}:{minutes:02d}"


def is_valid_time(raw: str) -> bool:
    try:
        parse_time(raw)
        return True
    except InvalidTimeError:
        return False


def today_label() -> str:
    return "Сегодня"


def date_label(dt: datetime | None = None) -> str:
    """Короткая подпись разделителя дат."""
    dt = dt or now_local()
    if dt.date() == now_local().date():
        return "Сегодня"
    return f"{dt.day} {RU_MONTHS_GEN[dt.month - 1]}"


def long_date(dt: datetime | None = None) -> str:
    dt = dt or now_local()
    return f"{dt.day} {RU_MONTHS_GEN[dt.month - 1]} {dt.year}"


def numeric_date(dt: datetime | None = None) -> str:
    dt = dt or now_local()
    return dt.strftime("%d.%m.%Y")


def weekday(dt: datetime | None = None) -> str:
    dt = dt or now_local()
    return RU_WEEKDAYS[dt.weekday()]


def datetime_to_ts(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


__all__ = [
    "now_local",
    "current_time_str",
    "parse_time",
    "is_valid_time",
    "date_label",
    "long_date",
    "numeric_date",
    "weekday",
    "today_label",
    "datetime_to_ts",
    "RU_MONTHS_GEN",
    "RU_MONTHS_SHORT",
    "RU_WEEKDAYS",
]
