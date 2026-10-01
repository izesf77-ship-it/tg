"""Сервис лимитов и антиспама.

Счётчики хранятся в SQLite (таблица ``usage_events``), поэтому
лимиты работают и после перезапуска бота.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.repositories import UsageRepository, UserRepository
from bot.models.base import utcnow
from bot.models.setting import Setting
from bot.models import AICreditBalance, StarPayment

logger = logging.getLogger(__name__)

KIND_IMAGE = "image"
KIND_IMAGE_ATTEMPT = "image_attempt"
KIND_AI = "ai"
KIND_AI_CREDIT = "ai_credit"
KIND_ACTION = "action"
_RATE_LOCKS = tuple(asyncio.Lock() for _ in range(64))

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
    credit_used: bool = False
    credit_payment_id: int | None = None

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

    @staticmethod
    def rate_lock(user_id: int) -> asyncio.Lock:
        return _RATE_LOCKS[int(user_id) % len(_RATE_LOCKS)]

    # --- Админские переопределения --------------------------------
    async def set_override(self, key: str, value: int) -> None:
        """Сохранить лимит в БД (и обновить кэш).

        Кэш обновляется ВСЕГДА, даже если сессии БД нет: иначе вызов
        падал с ``AttributeError: no attribute 'session'``, и новое
        значение лимита не применялось вовсе.
        """
        if key not in LIMIT_KEYS:
            raise ValueError("Неизвестный ключ лимита.")
        number = int(value)
        if number < 0 or (
            key in {"max_messages", "max_chats"} and number == 0
        ):
            raise ValueError("Недопустимое значение лимита.")
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
                value = int(row.value)
            except (TypeError, ValueError):
                continue
            if row.key not in LIMIT_KEYS or value < 0:
                continue
            if row.key in {"max_messages", "max_chats"} and value == 0:
                continue
            cached[row.key] = value
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

    async def reserve_image(self, user_id: int, premium: bool = False) -> LimitResult:
        async with self.rate_lock(user_id):
            check = await self.check_image(user_id, premium)
            if check:
                await self.log_image_attempt(user_id)
                await self.session.commit()
            return check

    async def reserve_ai(self, user_id: int, premium: bool = False) -> LimitResult:
        async with self.rate_lock(user_id):
            check = await self.check_ai(user_id, premium)
            if check:
                await self.log_ai(user_id)
                await self.session.commit()
                return check

            payment_result = await self.session.execute(
                select(StarPayment)
                .where(
                    StarPayment.user_id == int(user_id),
                    StarPayment.credits_remaining > 0,
                    StarPayment.refunded_at.is_(None),
                )
                .order_by(StarPayment.created_at, StarPayment.id)
                .limit(1)
            )
            credit_payment = payment_result.scalar_one_or_none()
            if credit_payment is not None:
                spent = await self.session.execute(
                    update(StarPayment)
                    .where(
                        StarPayment.id == credit_payment.id,
                        StarPayment.credits_remaining > 0,
                        StarPayment.refunded_at.is_(None),
                    )
                    .values(credits_remaining=StarPayment.credits_remaining - 1)
                )
                balance_spent = None
                if spent.rowcount:
                    balance_spent = await self.session.execute(
                        update(AICreditBalance)
                        .where(
                            AICreditBalance.user_id == int(user_id),
                            AICreditBalance.balance > 0,
                        )
                        .values(
                            balance=AICreditBalance.balance - 1,
                            updated_at=utcnow(),
                        )
                    )
            else:
                spent = None
                balance_spent = None
            if spent is not None and spent.rowcount and balance_spent and balance_spent.rowcount:
                await self.usage.log(user_id, KIND_AI_CREDIT)
                await self.session.commit()
                return LimitResult(
                    True,
                    check.used,
                    check.limit,
                    credit_used=True,
                    credit_payment_id=credit_payment.id,
                )
            if spent is not None and spent.rowcount:
                await self.session.rollback()
                logger.error(
                    "AI credit ledger and balance disagree (user=%s)",
                    user_id,
                )
            return LimitResult(
                False,
                check.used,
                check.limit,
                check.retry_after,
                "Часовой лимит AI исчерпан и купленных генераций нет. "
                "Выберите подходящий пакет в магазине: /premium",
            )

    async def refund_ai_credit(self, user_id: int, payment_id: int | None) -> None:
        """Restore a purchased AI credit when the provider failed."""
        if payment_id is None:
            raise ValueError("A purchased AI credit must be linked to its payment")
        await self.session.rollback()
        payment_result = await self.session.execute(
            update(StarPayment)
            .where(
                StarPayment.id == int(payment_id),
                StarPayment.user_id == int(user_id),
                StarPayment.refunded_at.is_(None),
            )
            .values(credits_remaining=StarPayment.credits_remaining + 1)
        )
        if not payment_result.rowcount:
            raise RuntimeError("The purchased AI credit can no longer be restored")
        result = await self.session.execute(
            update(AICreditBalance)
            .where(AICreditBalance.user_id == int(user_id))
            .values(
                balance=AICreditBalance.balance + 1,
                updated_at=utcnow(),
            )
        )
        if not result.rowcount:
            self.session.add(AICreditBalance(user_id=int(user_id), balance=1))
        await self.session.commit()

    async def _hourly(
        self, user_id: int, kind: str, limit: int
    ) -> LimitResult:
        since = utcnow() - timedelta(hours=1)
        if kind == KIND_IMAGE:
            used = await self.usage.count_since_kinds(
                user_id, (KIND_IMAGE, KIND_IMAGE_ATTEMPT), since
            )
        else:
            used = await self.usage.count_since(user_id, kind, since)
        if limit <= 0:
            return LimitResult(True, used, 0)
        if used < limit:
            return LimitResult(True, used, limit)
        if kind == KIND_IMAGE:
            last = await self.usage.last_event_kinds(
                user_id, (KIND_IMAGE, KIND_IMAGE_ATTEMPT)
            )
        else:
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

    async def log_image_attempt(self, user_id: int, meta: str | None = None) -> None:
        await self.usage.log(user_id, KIND_IMAGE_ATTEMPT, meta)

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
    "KIND_IMAGE_ATTEMPT",
    "KIND_AI",
    "KIND_AI_CREDIT",
    "KIND_ACTION",
    "LIMIT_KEYS",
]
