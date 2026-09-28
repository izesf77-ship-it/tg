"""События использования — источник данных для лимитов и статистики."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from bot.models.base import Base, UTCDateTime, utcnow


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    # image | ai | action | chat_created | render
    created_at: Mapped["UTCDateTime"] = mapped_column(
        UTCDateTime, default=utcnow, index=True, nullable=False
    )
    meta: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    __table_args__ = (Index("ix_usage_user_kind_time", "user_id", "kind", "created_at"),)


__all__ = ["UsageEvent"]
