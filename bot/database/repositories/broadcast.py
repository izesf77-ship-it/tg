"""Репозиторий рассылок."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Broadcast
from bot.models.base import utcnow


class BroadcastRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, admin_id: int, text: str) -> Broadcast:
        item = Broadcast(admin_id=int(admin_id), text=text, status="pending", created_at=utcnow())
        self.session.add(item)
        await self.session.flush()
        return item

    async def get(self, broadcast_id: int) -> Optional[Broadcast]:
        return await self.session.get(Broadcast, int(broadcast_id))

    async def update(self, item: Broadcast, **fields) -> Broadcast:
        for key, value in fields.items():
            setattr(item, key, value)
        self.session.add(item)
        await self.session.flush()
        return item

    async def finish(self, item: Broadcast, sent: int, failed: int) -> Broadcast:
        item.sent = sent
        item.failed = failed
        item.status = "done"
        item.finished_at = utcnow()
        self.session.add(item)
        await self.session.flush()
        return item

    async def list_recent(self, limit: int = 10) -> List[Broadcast]:
        result = await self.session.execute(
            select(Broadcast).order_by(Broadcast.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def count(self) -> int:
        from sqlalchemy import func

        res = await self.session.execute(select(func.count(Broadcast.id)))
        return int(res.scalar() or 0)


__all__ = ["BroadcastRepository"]
