"""Настройки приложения (ключ-значение).

Нужны, чтобы изменения из админ-панели (например, лимиты) сохранялись
между перезапусками и не терялись при создании нового экземпляра сервиса.
"""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from bot.models.base import Base, utcnow


class Setting(Base):
    """Произвольная настройка: ключ → значение (текст)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[str] = mapped_column(String(32), default=utcnow)


__all__ = ["Setting"]
