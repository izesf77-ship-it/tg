"""Хендлеры бота."""

from bot.handlers import admin, ai, create, editor, errors, menus, my_chats, start
from bot.handlers.errors import router as errors_router

__all__ = [
    "start",
    "menus",
    "create",
    "editor",
    "my_chats",
    "ai",
    "admin",
    "errors",
    "errors_router",
]
