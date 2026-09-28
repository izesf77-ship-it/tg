"""Переписка: черновик или сохранённый чат."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from bot.models.base import Base, UTCDateTime, utcnow


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(128), default="Переписка", nullable=False)
    style: Mapped[str] = mapped_column(String(32), default="telegram", nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_draft: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    template: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    renders_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped["UTCDateTime"] = mapped_column(
        UTCDateTime, default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped["UTCDateTime"] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped[Optional["User"]] = relationship("User", lazy="selectin")  # noqa: F821

    def to_summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "style": self.style,
            "message_count": self.message_count,
            "is_draft": self.is_draft,
            "template": self.template,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


__all__ = ["Chat"]
