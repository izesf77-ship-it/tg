"""Общие клавиатуры: главное меню, «Назад», скрытие клавиатуры."""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.utils import callbacks as C

BTN_CREATE = "➕ Создать переписку"
BTN_AI = "✨ Создать с AI"
BTN_MY = "📂 Мои переписки"
BTN_HELP = "📖 Как это работает"
BTN_SETTINGS = "⚙️ Настройки"
BTN_CANCEL = "❌ Отмена"
BTN_BACK = "⬅️ Назад"
BTN_PREMIUM = "⭐️ Premium"

MAIN_MENU_TEXT = (
    "👋 <b>Конструктор переписок</b>\n\n"
    "Создавай вымышленные диалоги, настраивай участников "
    "и получай готовый скриншот."
)


def main_menu() -> ReplyKeyboardMarkup:
    """Главное меню (ReplyKeyboard)."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CREATE)],
            [KeyboardButton(text=BTN_AI)],
            [KeyboardButton(text=BTN_MY), KeyboardButton(text=BTN_HELP)],
            [KeyboardButton(text=BTN_SETTINGS)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие…",
    )


def main_menu_inline() -> InlineKeyboardMarkup:
    """Главное меню кнопками (используется в /help и админке)."""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text=BTN_CREATE, callback_data=C.cb(C.S_MENU, "create")),
        InlineKeyboardButton(text=BTN_AI, callback_data=C.cb(C.S_AI, "ask")),
    )
    kb.row(
        InlineKeyboardButton(text=BTN_MY, callback_data=C.cb(C.S_MENU, "my")),
    )
    kb.row(
        InlineKeyboardButton(text=BTN_HELP, callback_data=C.cb(C.S_MENU, "help")),
        InlineKeyboardButton(
            text=BTN_SETTINGS, callback_data=C.cb(C.S_MENU, "settings")
        ),
    )
    return kb.as_markup()


def cancel_menu() -> ReplyKeyboardMarkup:
    """Клавиатура с единственной кнопкой отмены."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )


def input_menu(hint: str = "Отправьте значение…") -> ReplyKeyboardMarkup:
    """Клавиатура для режима ввода: отмена + подсказка."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
        input_field_placeholder=hint,
    )


def back_button(callback_data: str, text: str = BTN_BACK) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def with_back(
    builder: InlineKeyboardBuilder, callback_data: str, text: str = BTN_BACK
) -> InlineKeyboardBuilder:
    """Добавить кнопку «Назад» последней строкой."""
    builder.row(back_button(callback_data, text))
    return builder


def hide_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


__all__ = [
    "main_menu",
    "main_menu_inline",
    "main_menu_text",
    "cancel_menu",
    "input_menu",
    "back_button",
    "with_back",
    "hide_keyboard",
    "MAIN_MENU_TEXT",
    "BTN_CREATE",
    "BTN_AI",
    "BTN_MY",
    "BTN_HELP",
    "BTN_SETTINGS",
    "BTN_CANCEL",
    "BTN_BACK",
    "BTN_PREMIUM",
]
