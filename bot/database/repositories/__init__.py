"""Репозитории (доступ к данным)."""

from __future__ import annotations

from bot.database.repositories.broadcast import BroadcastRepository
from bot.database.repositories.chat import ChatRepository
from bot.database.repositories.stats import StatsRepository
from bot.database.repositories.usage import UsageRepository
from bot.database.repositories.user import UserRepository

__all__ = [
    "BroadcastRepository",
    "ChatRepository",
    "StatsRepository",
    "UsageRepository",
    "UserRepository",
]
