"""Сервис лимитов и антиспама.

Счётчики хранятся в SQLite (таблица ``usage_events``), поэтому
лимиты работают и после перезапуска бота.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.repositories import UsageRepository, UserRepository
from bot.models.base import utcnow
from bot.models.setting import Setting

logger = logging.getLogger(__name__)

KIND_IMAGE = "image"
KIND_AI = "ai"
KIND_ACTION = "action"

# Ключи лимитов, которые админ может менять из админ-панели
LIMIT_KEYS = (
    "limit_image_per_hour",
    "limit_ai_per_hour",
    "limit_image_per_hour_premium",
    "limit_ai_per_hour_premium",
    "limit_actions_per_minute",
    "max_messages",
    "max_chats",
)

# Переопределения в памяти: переживают пересоздание LimitService на каждом
# апдейте (bind() вызывается в middleware на каждое событие).
cached: dict[str, int] = {}
_loaded = False


@dataclass
class LimitResult:
    """Результат проверки лимита."""

    allowed: bool
    used: int = 0
    limit: int = 0
    retry_after: int = 0
    text: str = ""

    def __bool__(self) -> bool:
        return self.allowed


class LimitService:
    """Сервис лимитов.

    Переопределения из админ-панели хранятся в БД (таблица ``settings``)
    и кэшируются в памяти. Раньше они жили в ``self._overrides``, но сервис
    пересоздаётся на каждое событие (``bind()``), поэтому любое изменение
    из админки исчезало уже на следующем апдейте.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.usage = UsageRepository(session)
        self.users = UserRepository(session)

    # --- Админские переопределения --------------------------------
    async def set_override(self, key: str, value: int) -> None:
        """Сохранить лимит в БД (и обновить кэш).

        Кэш обновляется ВСЕГДА, даже если сессии БД нет: иначе вызов
        падал с ``AttributeError: no attribute 'session'``, и новое
        значение лимита не применялось вовсе.
        """
        number = int(value)
        cached[key] = number
        session = getattr(self, "session", None)
        if session is None:
            logger.warning("Сессия БД недоступна: лимит %s применён только в памяти", key)
            return
        row = await session.get(Setting, key)
        if row is None:
            session.add(Setting(key=key, value=str(number)))
        else:
            row.value = str(number)
            row.updated_at = utcnow()
        await session.commit()
        logger.info("Лимит %s = %s (сохранён в БД)", key, number)

    async def reset_overrides(self) -> int:
        """Сбросить все переопределения к значениям из .env."""
        count = len(cached)
        cached.clear()
        await self.session.execute(delete(Setting))
        await self.session.commit()
        return count

    async def load_overrides(self) -> dict[str, int]:
        """Загрузить переопределения из БД в кэш."""
        result = await self.session.execute(select(Setting))
        for row in result.scalars().all():
            try:
                cached[row.key] = int(row.value)
            except (TypeError, ValueError):
                continue
        return dict(cached)

    def value(self, key: str) -> int:
        if key in cached:
            return cached[key]
        return int(getattr(settings, key, 0))

    def overrides(self) -> dict[str, int]:
        return dict(cached)

    # --- Проверки ---------------------------------------------------
    async def check_image(self, user_id: int, premium: bool = False) -> LimitResult:
        key = "limit_image_per_hour_premium" if premium else "limit_image_per_hour"
        return await self._hourly(user_id, KIND_IMAGE, self.value(key))

    async def check_ai(self, user_id: int, premium: bool = False) -> LimitResult:
        key = "limit_ai_per_hour_premium" if premium else "limit_ai_per_hour"
        return await self._hourly(user_id, KIND_AI, self.value(key))

    async def _hourly(
        self, user_id: int, kind: str, limit: int
    ) -> LimitResult:
        since = utcnow() - timedelta(hours=1)
        used = await self.usage.count_since(user_id, kind, since)
        if limit <= 0:
            return LimitResult(True, used, 0)
        if used < limit:
            return LimitResult(True, used, limit)
        last = await self.usage.last_event(user_id, kind)
        retry = self._retry_after(last)
        return LimitResult(
            False,
            used,
            limit,
            retry,
            f"Лимит исчерпан: {used}/{limit} в час. Попробуйте через {retry} мин.",
        )

    @staticmethod
    def _retry_after(last: Optional[datetime]) -> int:
        if last is None:
            return 60
        elapsed = (utcnow() - last).total_seconds()
        return max(1, int((3600 - elapsed) / 60) + 1)

    async def check_spam(self, user_id: int) -> LimitResult:
        """Защита от спама: не более N действий в минуту."""
        limit = self.value("limit_actions_per_minute")
        since = utcnow() - timedelta(minutes=1)
        used = await self.usage.count_since(user_id, KIND_ACTION, since)
        if limit <= 0 or used < limit:
            return LimitResult(True, used, limit)
        return LimitResult(
            False, used, limit, 1, "Слишком много действий. Подождите минуту."
        )

    # --- Фиксация событий -------------------------------------------
    async def log(self, user_id: int, kind: str, meta: str | None = None) -> None:
        await self.usage.log(user_id, kind, meta)

    async def log_action(self, user_id: int, meta: str | None = None) -> None:
        await self.usage.log(user_id, KIND_ACTION, meta)

    async def log_image(self, user_id: int, meta: str | None = None) -> None:
        await self.usage.log(user_id, KIND_IMAGE, meta)

    async def log_ai(self, user_id: int, meta: str | None = None) -> None:
        await self.usage.log(user_id, KIND_AI, meta)

    # --- Прочие лимиты -----------------------------------------------
    def max_messages(self, premium: bool) -> int:
        limit = self.value("max_messages")
        if premium:
            return max(limit, 500)
        return limit

    def max_chats(self, premium: bool) -> int:
        limit = self.value("max_chats")
        return limit * 3 if premium else limit


limit_service: Optional[LimitService] = None


def bind(session: AsyncSession) -> LimitService:
    """Создать сервис для сессии; лимиты из БД грузятся один раз (см. ensure_loaded)."""
    global limit_service
    limit_service = LimitService(session)
    return limit_service


async def ensure_loaded() -> dict[str, int]:
    """Загрузить переопределения из БД при первом обращении."""
    global _loaded
    if _loaded:
        return dict(cached)
    _loaded = True
    if limit_service is not None:
        try:
            await limit_service.load_overrides()
        except Exception as exc:  # noqa: BLE001
            _loaded = False
            logger.warning("Не удалось загрузить лимиты из БД: %s", exc)
    return dict(cached)


__all__ = [
    "LimitService",
    "LimitResult",
    "bind",
    "ensure_loaded",
    "cached",
    "KIND_IMAGE",
    "KIND_AI",
    "KIND_ACTION",
    "LIMIT_KEYS",
]
