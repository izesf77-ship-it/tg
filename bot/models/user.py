"""Пользователь бота."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from bot.models.base import Base, UTCDateTime, utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    language: Mapped[str] = mapped_column(String(8), default="ru")

    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    total_images: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_ai: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_chats: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_actions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped["UTCDateTime"] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    last_activity: Mapped["UTCDateTime"] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
    premium_until: Mapped[Optional["UTCDateTime"]] = mapped_column(UTCDateTime, nullable=True)

    @property
    def display_name(self) -> str:
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name or self.username or str(self.id)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "name": self.display_name,
            "premium": self.is_premium,
            "banned": self.is_banned,
            "images": self.total_images,
            "ai": self.total_ai,
            "chats": self.total_chats,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
        }


__all__ = ["User"]
