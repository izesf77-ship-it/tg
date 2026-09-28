"""Базовый декларативный класс."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import DateTime


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UTCDateTime(DateTime):
    """DateTime, который всегда отдаёт naive UTC (удобно для SQLite)."""

    def process_result_value(self, value, dialect):  # noqa: D102
        if value is not None and value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value


class Base(DeclarativeBase):
    pass
