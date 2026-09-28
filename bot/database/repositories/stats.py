"""Агрегированная статистика для админ-панели."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Dict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Chat, UsageEvent, User
from bot.models.base import utcnow


@dataclass
class AdminStats:
    users: int = 0
    users_today: int = 0
    active_24h: int = 0
    active_7d: int = 0
    chats: int = 0
    chats_today: int = 0
    drafts: int = 0
    images: int = 0
    images_today: int = 0
    ai: int = 0
    ai_today: int = 0
    actions: int = 0
    top_users: list = field(default_factory=list)
    styles: Dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "users": self.users,
            "users_today": self.users_today,
            "active_24h": self.active_24h,
            "active_7d": self.active_7d,
            "chats": self.chats,
            "chats_today": self.chats_today,
            "drafts": self.drafts,
            "images": self.images,
            "images_today": self.images_today,
            "ai": self.ai,
            "ai_today": self.ai_today,
            "actions": self.actions,
        }


class StatsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def collect(self) -> AdminStats:
        now = utcnow()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week = now - timedelta(days=7)
        day_ago = now - timedelta(hours=24)
        stats = AdminStats()

        async def count(model, *where):
            stmt = select(func.count()).select_from(model)
            if where:
                stmt = stmt.where(*where)
            res = await self.session.execute(stmt)
            return int(res.scalar() or 0)

        stats.users = await count(User)
        stats.users_today = await count(User, User.created_at >= today)
        stats.active_24h = await count(User, User.last_activity >= day_ago)
        stats.active_7d = await count(User, User.last_activity >= week)
        stats.chats = await count(Chat)
        stats.chats_today = await count(Chat, Chat.created_at >= today)
        stats.drafts = await count(Chat, Chat.is_draft.is_(True))
        stats.images = await count(UsageEvent, UsageEvent.kind == "image")
        stats.images_today = await count(
            UsageEvent, UsageEvent.kind == "image", UsageEvent.created_at >= today
        )
        stats.ai = await count(UsageEvent, UsageEvent.kind == "ai")
        stats.ai_today = await count(
            UsageEvent, UsageEvent.kind == "ai", UsageEvent.created_at >= today
        )
        stats.actions = await count(UsageEvent, UsageEvent.kind == "action")

        top = await self.session.execute(
            select(UsageEvent.user_id, func.count(UsageEvent.id).label("cnt"))
            .where(UsageEvent.kind == "image")
            .group_by(UsageEvent.user_id)
            .order_by(func.count(UsageEvent.id).desc())
            .limit(10)
        )
        stats.top_users = [(row[0], int(row[1])) for row in top.all()]

        styles = await self.session.execute(
            select(Chat.style, func.count(Chat.id)).group_by(Chat.style)
        )
        stats.styles = {str(row[0] or "unknown"): int(row[1]) for row in styles.all()}

        return stats


__all__ = ["StatsRepository", "AdminStats"]
