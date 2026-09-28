"""Запись о рассылке."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from bot.models.base import Base, UTCDateTime, utcnow


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped["UTCDateTime"] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    finished_at: Mapped[Optional["UTCDateTime"]] = mapped_column(UTCDateTime, nullable=True)

    __table_args__ = ()


__all__ = ["Broadcast"]
