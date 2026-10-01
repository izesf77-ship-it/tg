"""Репозиторий событий использования (лимиты)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import UsageEvent
from bot.models.base import utcnow


class UsageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log(
        self, user_id: int, kind: str, meta: str | None = None
    ) -> UsageEvent:
        event = UsageEvent(user_id=int(user_id), kind=kind, meta=meta, created_at=utcnow())
        self.session.add(event)
        await self.session.flush()
        return event

    async def count_since(
        self, user_id: int, kind: str, since: Optional[datetime] = None
    ) -> int:
        since = since or (utcnow() - timedelta(hours=1))
        result = await self.session.execute(
            select(func.count(UsageEvent.id)).where(
                UsageEvent.user_id == int(user_id),
                UsageEvent.kind == kind,
                UsageEvent.created_at >= since,
            )
        )
        return int(result.scalar() or 0)

    async def count_since_kinds(
        self, user_id: int, kinds: tuple[str, ...], since: datetime
    ) -> int:
        result = await self.session.execute(
            select(func.count(UsageEvent.id)).where(
                UsageEvent.user_id == int(user_id),
                UsageEvent.kind.in_(kinds),
                UsageEvent.created_at >= since,
            )
        )
        return int(result.scalar() or 0)

    async def count_all(self, kind: str) -> int:
        result = await self.session.execute(
            select(func.count(UsageEvent.id)).where(UsageEvent.kind == kind)
        )
        return int(result.scalar() or 0)

    async def last_event(self, user_id: int, kind: str) -> Optional[datetime]:
        result = await self.session.execute(
            select(UsageEvent.created_at)
            .where(UsageEvent.user_id == int(user_id), UsageEvent.kind == kind)
            .order_by(UsageEvent.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def last_event_kinds(
        self, user_id: int, kinds: tuple[str, ...]
    ) -> Optional[datetime]:
        result = await self.session.execute(
            select(UsageEvent.created_at)
            .where(
                UsageEvent.user_id == int(user_id),
                UsageEvent.kind.in_(kinds),
            )
            .order_by(UsageEvent.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def purge_old(self, days: int = 30) -> int:
        """Удалить старые события (вызывается при старте)."""
        threshold = utcnow() - timedelta(days=days)
        result = await self.session.execute(
            delete(UsageEvent).where(UsageEvent.created_at < threshold)
        )
        await self.session.flush()
        return int(result.rowcount or 0)


__all__ = ["UsageRepository"]
