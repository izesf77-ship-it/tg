"""Сервисный слой приложения."""

from bot.services.ai_service import AIService, ai_service
from bot.services.chat_service import ChatService, chat_service
from bot.services.limit_service import LimitService, limit_service
from bot.services.premium_service import PremiumService, premium_service
from bot.services.render_service import RenderService, render_service
from bot.services.templates_service import TemplatesService, templates_service
from bot.services.user_service import UserService, user_service

__all__ = [
    "AIService",
    "ai_service",
    "ChatService",
    "chat_service",
    "LimitService",
    "limit_service",
    "PremiumService",
    "premium_service",
    "RenderService",
    "render_service",
    "TemplatesService",
    "templates_service",
    "UserService",
    "user_service",
]
