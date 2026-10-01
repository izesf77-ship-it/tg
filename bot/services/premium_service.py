"""Premium access rules and feature descriptions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
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
        if not bool(getattr(user, "is_premium", False)):
            return False
        until = getattr(user, "premium_until", None)
        if until is None:
            return True
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return until > now

    def features(self) -> List[PremiumFeature]:
        return list(FEATURES)

    def max_messages(self, user) -> int:
        return 500 if self.is_premium(user) else settings.max_messages

premium_service = PremiumService()

__all__ = ["PremiumService", "PremiumFeature", "FEATURES", "premium_service"]
