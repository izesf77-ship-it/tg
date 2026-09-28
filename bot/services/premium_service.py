"""Подготовка к монетизации (Telegram Stars).

Платежи пока не подключены, но вся логика Premium вынесена сюда,
чтобы позже достаточно было реализовать ``create_invoice_link``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

from bot.config import settings

logger = logging.getLogger(__name__)


@dataclass
class PremiumFeature:
    key: str
    title: str
    free: str
    premium: str


FEATURES: List[PremiumFeature] = [
    PremiumFeature("generations", "Генерации в час", "20", "100"),
    PremiumFeature("ai", "AI-сценариев в час", "5", "30"),
    PremiumFeature("styles", "Стили интерфейса", "4 из 5", "Все 5"),
    PremiumFeature("messages", "Сообщений в переписке", "200", "500"),
    PremiumFeature("templates", "Шаблоны", "Базовые", "Все, включая премиум"),
    PremiumFeature("media", "Медиа-элементы", "Базовые", "Все + голосовые/файлы"),
    PremiumFeature("ad", "Рекламное сообщение", "Показывается", "Нет"),
]


class PremiumService:
    """Логика Premium и заглушка платежей."""

    @property
    def enabled(self) -> bool:
        return bool(settings.premium_enabled)

    @property
    def stars_price(self) -> int:
        return int(settings.premium_stars_price)

    def is_premium(self, user) -> bool:
        return bool(getattr(user, "is_premium", False))

    def features(self) -> List[PremiumFeature]:
        return list(FEATURES)

    def max_messages(self, user) -> int:
        return 500 if self.is_premium(user) else settings.max_messages

    def async_quote(self) -> str:
        """Текст о предстоящей оплате (без подключения платёжного провайдера)."""
        return (
            "⭐️ <b>Premium</b>\n\n"
            f"Оплата через Telegram Stars ({self.stars_price} ⭐️) — "
            "скоро будет доступна.\n\n"
            "Пока можно пользоваться бесплатным лимитом.\n"
            "Монетизация подготовлена в коде: добавление оплаты "
            "не потребует изменения архитектуры."
        )

    async def create_invoice_link(self, bot, user_id: int) -> str:
        """Заглушка под Telegram Stars.

        Для включения достаточно реализовать вызов
        ``bot.send_invoice`` с ``currency='XTR'`` и ``provider_token=''``.
        """
        raise NotImplementedError(
            "Оплата пока не подключена. Включите её в PremiumService.create_invoice_link."
        )


premium_service = PremiumService()

__all__ = ["PremiumService", "PremiumFeature", "FEATURES", "premium_service"]
