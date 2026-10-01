"""Сервис работы с пользователями (регистрация, статистика, премиум)."""

from __future__ import annotations

import logging
from typing import Optional

from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.repositories import UserRepository
from bot.models import User
from bot.models.base import utcnow
from bot.services.premium_service import premium_service

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = UserRepository(session)

    async def register(self, tg_user: TgUser) -> User:
        """Найти или создать пользователя при первом обращении."""
        user, is_new = await self.repo.get_or_create(
            user_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            language=tg_user.language_code or "ru",
            is_admin=settings.is_admin(tg_user.id),
        )
        if is_new:
            logger.info("Новый пользователь: %s (%s)", user.id, user.username or "-")
        if user.is_premium and user.premium_until and user.premium_until <= utcnow():
            user.is_premium = False
            user.premium_until = None
            self.session.add(user)
            await self.session.flush()
        return user

    async def get(self, user_id: int) -> Optional[User]:
        return await self.repo.get(user_id)

    async def is_banned(self, user_id: int) -> bool:
        user = await self.repo.get(user_id)
        return bool(user and user.is_banned)

    async def is_premium(self, user_id: int) -> bool:
        user = await self.repo.get(user_id)
        return premium_service.is_premium(user)

    async def is_admin(self, user_id: int) -> bool:
        user = await self.repo.get(user_id)
        if user and user.is_admin:
            return True
        return settings.is_admin(user_id)

    async def count_image(self, user_id: int, amount: int = 1) -> None:
        await self.repo.increment(user_id, "total_images", amount)

    async def count_ai(self, user_id: int, amount: int = 1) -> None:
        await self.repo.increment(user_id, "total_ai", amount)

    async def count_action(self, user_id: int, amount: int = 1) -> None:
        await self.repo.increment(user_id, "total_actions", amount)

    async def count_chat(self, user_id: int, amount: int = 1) -> None:
        await self.repo.increment(user_id, "total_chats", amount)

    async def set_premium(self, user_id: int, value: bool) -> None:
        await self.repo.set_premium(user_id, value)
        logger.info("Premium для %s: %s", user_id, value)


user_service: UserService | None = None  # создаётся в middleware


def bind(session: AsyncSession) -> UserService:
    global user_service
    user_service = UserService(session)
    return user_service


__all__ = ["UserService", "bind"]
