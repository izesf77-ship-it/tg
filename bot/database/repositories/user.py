"""Репозиторий пользователей."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import User
from bot.models.base import utcnow


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: int) -> Optional[User]:
        return await self.session.get(User, int(user_id))

    async def get_or_create(
        self,
        user_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        language: str = "ru",
        is_admin: bool = False,
    ) -> User:
        user = await self.get(user_id)
        now = utcnow()
        if user is None:
            user = User(
                id=int(user_id),
                username=username,
                first_name=first_name,
                last_name=last_name,
                language=language or "ru",
                is_admin=is_admin,
                created_at=now,
                last_activity=now,
            )
            self.session.add(user)
            await self.session.flush()
            return user

        changed = False
        if username and user.username != username:
            user.username = username
            changed = True
        if first_name and user.first_name != first_name:
            user.first_name = first_name
            changed = True
        if last_name is not None and user.last_name != last_name:
            user.last_name = last_name
            changed = True
        if is_admin and not user.is_admin:
            user.is_admin = True
            changed = True
        if user.last_activity is None or (now - user.last_activity) > timedelta(seconds=30):
            user.last_activity = now
            changed = True
        if changed:
            self.session.add(user)
            await self.session.flush()
        return user

    async def touch(self, user_id: int) -> None:
        user = await self.get(user_id)
        if user:
            user.last_activity = utcnow()
            self.session.add(user)
            await self.session.flush()

    async def increment(self, user_id: int, field: str, amount: int = 1) -> None:
        if field not in {
            "total_images",
            "total_ai",
            "total_chats",
            "total_actions",
        }:
            raise ValueError(f"Недопустимое поле счётчика пользователя: {field}")
        column = getattr(User, field)
        await self.session.execute(
            update(User)
            .where(User.id == int(user_id))
            .values({field: func.max(0, column + int(amount))})
        )
        await self.session.flush()

    async def set_premium(self, user_id: int, value: bool) -> None:
        user = await self.get(user_id)
        if user:
            user.is_premium = bool(value)
            self.session.add(user)
            await self.session.flush()

    async def set_banned(self, user_id: int, value: bool) -> None:
        user = await self.get(user_id)
        if user:
            user.is_banned = bool(value)
            self.session.add(user)
            await self.session.flush()

    async def count(self) -> int:
        result = await self.session.execute(select(func.count(User.id)))
        return int(result.scalar() or 0)

    async def count_new_today(self) -> int:
        start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self.session.execute(
            select(func.count(User.id)).where(User.created_at >= start)
        )
        return int(result.scalar() or 0)

    async def count_active(self, hours: int = 24) -> int:
        since = utcnow() - timedelta(hours=hours)
        result = await self.session.execute(
            select(func.count(User.id)).where(User.last_activity >= since)
        )
        return int(result.scalar() or 0)

    async def iter_all(self, limit: int | None = None):
        stmt = select(User).order_by(User.last_activity.desc())
        if limit:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def page(self, offset: int, limit: int) -> list[User]:
        result = await self.session.execute(
            select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all())


__all__ = ["UserRepository", "datetime"]
