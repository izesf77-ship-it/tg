"""Клавиатуры админ-панели."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.utils import callbacks as C

BACK_ADMIN = C.cb(C.S_ADMIN, "home")


def admin_menu() -> InlineKeyboardMarkup:
    """Главное меню админки."""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data=C.cb(C.S_ADMIN, "stats")),
        InlineKeyboardButton(text="👥 Пользователи", callback_data=C.cb(C.S_ADMIN, "users")),
    )
    kb.row(
        InlineKeyboardButton(
            text="📢 Рассылка", callback_data=C.cb(C.S_ADMIN, "broadcast")
        ),
        InlineKeyboardButton(text="⚙️ Лимиты", callback_data=C.cb(C.S_ADMIN, "limits")),
    )
    kb.row(
        InlineKeyboardButton(text="⬅️ В меню бота", callback_data=C.cb(C.S_MENU, "home"))
    )
    return kb.as_markup()


def users_page(page: int, pages: int) -> InlineKeyboardMarkup:
    """Навигация по списку пользователей."""
    kb = InlineKeyboardBuilder()
    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(text="◀️", callback_data=C.cb(C.S_ADMIN, "users", page - 1))
        )
    nav.append(
        InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data=C.cb(C.S_ADMIN, "noop"))
    )
    if page + 1 < pages:
        nav.append(
            InlineKeyboardButton(text="▶️", callback_data=C.cb(C.S_ADMIN, "users", page + 1))
        )
    kb.row(*nav)
    kb.row(InlineKeyboardButton(text="⬅️ Админка", callback_data=BACK_ADMIN))
    return kb.as_markup()


def broadcast_confirm(broadcast_id: int, total: int) -> InlineKeyboardMarkup:
    """Подтверждение рассылки (отправка не начнётся без нажатия)."""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text=f"✅ Отправить ({total})", callback_data=C.cb(C.S_ADMIN, "send", broadcast_id)
        ),
        InlineKeyboardButton(
            text="❌ Отменить", callback_data=C.cb(C.S_ADMIN, "cancel_send", broadcast_id)
        ),
    )
    return kb.as_markup()


def limits_menu(limits: dict) -> InlineKeyboardMarkup:
    """Меню изменения лимитов."""
    kb = InlineKeyboardBuilder()
    keys = [
        ("limit_image_per_hour", "🖼 Генераций/час"),
        ("limit_ai_per_hour", "✨ AI/час"),
        ("limit_image_per_hour_premium", "⭐️ Генераций/час (Pro)"),
        ("limit_ai_per_hour_premium", "⭐️ AI/час (Pro)"),
        ("limit_actions_per_minute", "⏱ Действий/мин"),
        ("max_messages", "💬 Макс. сообщений"),
        ("max_chats", "📂 Макс. переписок"),
    ]
    for key, label in keys:
        value = limits.get(key, 0)
        kb.row(
            InlineKeyboardButton(
                text=f"{label}: {value}",
                callback_data=C.cb(C.S_ADMIN, "limit", key),
            )
        )
    kb.row(
        InlineKeyboardButton(
            text="♻️ Сбросить к значениям из .env",
            callback_data=C.cb(C.S_ADMIN, "limits_reset"),
        )
    )
    kb.row(InlineKeyboardButton(text="⬅️ Админка", callback_data=BACK_ADMIN))
    return kb.as_markup()


__all__ = [
    "BACK_ADMIN",
    "admin_menu",
    "users_page",
    "broadcast_confirm",
    "limits_menu",
]
