"""Клавиатуры: мои переписки, AI-сценарии, настройки, «как это работает»."""

from __future__ import annotations

from typing import List

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboards.common import with_back
from bot.models import Chat
from bot.utils import callbacks as C

BACK_HOME = C.cb(C.S_MENU, "home")
PAGE_SIZE = 5


def chats_list(
    chats: List[Chat], page: int = 0, total: int = 0, page_size: int = PAGE_SIZE
) -> InlineKeyboardMarkup:
    """Список сохранённых переписок: Открыть / Дублировать / Удалить."""
    kb = InlineKeyboardBuilder()
    if not chats:
        kb.row(
            InlineKeyboardButton(
                text="➕ Создать первую", callback_data=C.cb(C.S_MENU, "create")
            )
        )
        return with_back(kb, BACK_HOME).as_markup()

    for chat in chats:
        title = chat.title or "Переписка"
        header = f"#{chat.id} {title} · {chat.message_count} сообщ."
        kb.row(
            InlineKeyboardButton(
                text=header[:60], callback_data=C.cb(C.S_MY, "open", chat.id)
            )
        )
        kb.row(
            InlineKeyboardButton(
                text="📂 Открыть", callback_data=C.cb(C.S_MY, "open", chat.id)
            ),
            InlineKeyboardButton(
                text="📋 Дублировать", callback_data=C.cb(C.S_MY, "dup", chat.id)
            ),
            InlineKeyboardButton(
                text="🗑 Удалить", callback_data=C.cb(C.S_MY, "del", chat.id)
            ),
        )

    pages = max(1, (total + page_size - 1) // page_size)
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(
                InlineKeyboardButton(
                    text="◀️", callback_data=C.cb(C.S_MY, "page", page - 1)
                )
            )
        nav.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{pages}", callback_data=C.cb(C.S_MY, "noop")
            )
        )
        if page + 1 < pages:
            nav.append(
                InlineKeyboardButton(
                    text="▶️", callback_data=C.cb(C.S_MY, "page", page + 1)
                )
            )
        kb.row(*nav)
    return with_back(kb, BACK_HOME).as_markup()


def confirm_delete_chat(chat_id: int) -> InlineKeyboardMarkup:
    """Подтверждение удаления переписки."""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="✅ Да, удалить", callback_data=C.cb(C.S_MY, "del_yes", chat_id)
        ),
        InlineKeyboardButton(text="↩️ Отмена", callback_data=C.cb(C.S_MY, "cancel_del")),
    )
    return kb.as_markup()


def ai_menu(enabled: bool) -> InlineKeyboardMarkup:
    """Экран AI-генерации сценария."""
    kb = InlineKeyboardBuilder()
    if enabled:
        kb.row(
            InlineKeyboardButton(
                text="✨ Создать сценарий", callback_data=C.cb(C.S_AI, "ask")
            )
        )
    else:
        kb.row(
            InlineKeyboardButton(
                text="ℹ️ Почему недоступно", callback_data=C.cb(C.S_AI, "why")
            )
        )
    return with_back(kb, BACK_HOME).as_markup()


def chat_settings_menu(chat_id: int) -> InlineKeyboardMarkup:
    """Настройки конкретной переписки."""
    kb = InlineKeyboardBuilder()
    options = [
        ("style", "🎨 Стиль интерфейса"),
        ("time", "🕐 Показывать время"),
        ("checks", "✓ Галочки прочтения"),
        ("read", "👁 Синие галочки (прочитано)"),
        ("reactions", "❤️ Реакции"),
        ("avatars", "🖼 Аватары в списке"),
        ("tail", "🔻 Хвостики пузырей"),
        ("pattern", "🎭 Фоновый узор"),
        ("dividers", "📅 Разделители дат"),
        ("disclaimer", "⚠️ Пометка FICTIONAL CHAT"),
    ]
    for key, label in options:
        kb.row(
            InlineKeyboardButton(
                text=label, callback_data=C.cb(C.S_EDIT, "setopt", key, chat_id)
            )
        )
    kb.row(
        InlineKeyboardButton(
            text="🗑 Очистить сообщения", callback_data=C.cb(C.S_EDIT, "clear", chat_id)
        )
    )
    return with_back(kb, C.cb(C.S_EDIT, "back", chat_id)).as_markup()


def toggle_menu(option: str, chat_id: int, current: bool) -> InlineKeyboardMarkup:
    """Переключатель настройки."""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="✅ Включено" if current else "❌ Выключено",
            callback_data=C.cb(C.S_EDIT, "setopt", option, chat_id),
        )
    )
    return with_back(kb, C.cb(C.S_EDIT, "settings", chat_id)).as_markup()


def style_picker(chat_id: int, current: str, premium: bool) -> InlineKeyboardMarkup:
    """Выбор стиля внутри настроек переписки."""
    from bot.generators import AVAILABLE_STYLES

    kb = InlineKeyboardBuilder()
    for style in AVAILABLE_STYLES:
        mark = "✅ " if style.key == current else ""
        label = f"{mark}{style.title}"
        if style.premium_only and not premium:
            label = f"🔒 {label}"
        kb.row(
            InlineKeyboardButton(
                text=label, callback_data=C.cb(C.S_EDIT, "setstyle", style.key, chat_id)
            )
        )
    return with_back(kb, C.cb(C.S_EDIT, "settings", chat_id)).as_markup()


def disclaimer_picker(chat_id: int, current: str) -> InlineKeyboardMarkup:
    """Выбор текста пометки о вымышленном характере переписки."""
    kb = InlineKeyboardBuilder()
    options = [
        ("FICTIONAL", "🇬🇧 FICTIONAL CHAT"),
        ("ВЫМЫШЛЕННАЯ", "🇷🇺 ВЫМЫШЛЕННАЯ ПЕРЕПИСКА"),
        ("FICTIONAL_CHAT_ВЫМЫШЛЕННАЯ_ПЕРЕПИСКА", "🌍 Оба варианта"),
    ]
    for value, label in options:
        mark = "✅ " if current.startswith(value.split("_")[0][:6]) else ""
        kb.row(
            InlineKeyboardButton(
                text=f"{mark}{label}",
                callback_data=C.cb(C.S_EDIT, "setdisc", value, chat_id),
            )
        )
    return with_back(kb, C.cb(C.S_EDIT, "settings", chat_id)).as_markup()


def global_settings_menu() -> InlineKeyboardMarkup:
    """Настройки бота (не переписки)."""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="📊 Мои лимиты", callback_data=C.cb(C.S_SETTINGS, "limits"))
    )
    kb.row(
        InlineKeyboardButton(
            text="⭐️ Premium", callback_data=C.cb(C.S_SETTINGS, "premium")
        ),
        InlineKeyboardButton(
            text="🗑 Удалить мои данные", callback_data=C.cb(C.S_SETTINGS, "wipe")
        ),
    )
    kb.row(
        InlineKeyboardButton(
            text="ℹ️ О боте и правилах", callback_data=C.cb(C.S_MENU, "help")
        )
    )
    return with_back(kb, BACK_HOME).as_markup()


def help_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="🎬 Примеры (шаблоны)", callback_data=C.cb(C.S_TPL, "list")
        )
    )
    return with_back(kb, BACK_HOME).as_markup()


def confirm_wipe() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="✅ Да, удалить", callback_data=C.cb(C.S_SETTINGS, "wipe_yes")
        )
    )
    return kb.as_markup()


__all__ = [
    "BACK_HOME",
    "PAGE_SIZE",
    "chats_list",
    "confirm_delete_chat",
    "ai_menu",
    "chat_settings_menu",
    "toggle_menu",
    "style_picker",
    "disclaimer_picker",
    "global_settings_menu",
    "help_menu",
    "confirm_wipe",
]