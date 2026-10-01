"""Клавиатуры: создание переписки (стиль, участники, шаблоны)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.generators import AVAILABLE_STYLES
from bot.keyboards.common import with_back
from bot.utils import callbacks as C

STYLE_EMOJI = {
    "telegram": "✈️",
    "telegram_dark": "🌙",
    "whatsapp": "💬",
    "messenger": "💙",
    "simple": "▫️",
}

BACK_CREATE = C.cb(C.S_MENU, "home")


def style_menu(premium: bool = False) -> InlineKeyboardMarkup:
    """Шаг 1: выбор стиля интерфейса."""
    kb = InlineKeyboardBuilder()
    for style in AVAILABLE_STYLES:
        if style.premium_only and not premium:
            label = f"🔒 {STYLE_EMOJI.get(style.key, '•')} {style.title}"
        else:
            label = f"{STYLE_EMOJI.get(style.key, '•')} {style.title}"
        kb.row(
            InlineKeyboardButton(
                text=label,
                callback_data=C.cb(C.S_STYLE, "pick", style.key),
            )
        )
    kb.row(
        InlineKeyboardButton(
            text="✨ Создать сценарий с AI",
            callback_data=C.cb(C.S_AI, "ask"),
        )
    )
    return with_back(kb, BACK_CREATE).as_markup()


def participants_menu(
    config, chat_id: int, can_continue: bool = True
) -> InlineKeyboardMarkup:
    """Шаг 2: настройка участников."""
    kb = InlineKeyboardBuilder()
    for index, participant in enumerate(config.participants):
        mark = "⭐️" if participant.premium else ""
        name = participant.name or f"Участник {index + 1}"
        kb.row(
            InlineKeyboardButton(
                text=f"👤 {name} {mark}".strip(),
                callback_data=C.cb(C.S_PART, "open", index, chat_id),
            )
        )
    if can_continue:
        kb.row(
            InlineKeyboardButton(
                text="➡️ Продолжить",
                callback_data=C.cb(C.S_PART, "next", chat_id),
            )
        )
    return with_back(kb, C.cb(C.S_STYLE, "back")).as_markup()


def participant_card(index: int, participant, chat_id: int) -> InlineKeyboardMarkup:
    """Карточка участника: изменение полей."""
    kb = InlineKeyboardBuilder()
    fields = [
        ("name", "✏️ Имя"),
        ("username", "🔗 Username"),
        ("display_name", "🏷️ Отображаемое имя"),
        ("avatar", "🖼 Фотография"),
        ("status", "💬 Статус"),
        ("last_seen", "🕐 Время последнего входа"),
        ("premium", "⭐️ Premium"),
    ]
    for key, label in fields:
        kb.row(
            InlineKeyboardButton(
                text=label,
                callback_data=C.cb(C.S_PART, "field", index, key, chat_id),
            )
        )
    kb.row(
        InlineKeyboardButton(
            text="🗑 Сбросить участника",
            callback_data=C.cb(C.S_PART, "reset", index, chat_id),
        )
    )
    return with_back(kb, C.cb(C.S_PART, "back", chat_id)).as_markup()


def participant_field_skip(field: str, index: int, chat_id: int) -> InlineKeyboardMarkup:
    """Экран ввода поля участника с возможностью пропустить."""
    kb = InlineKeyboardBuilder()
    if field == "avatar":
        kb.row(
            InlineKeyboardButton(
                text="🎲 Случайный цвет",
                callback_data=C.cb(C.S_PART, "gen_avatar", index, chat_id),
            )
        )
    if field == "premium":
        kb.row(
            InlineKeyboardButton(
                text="✅ Да" if field else "❌ Нет",
                callback_data=C.cb(C.S_PART, "set_premium", index, 1, chat_id),
            ),
            InlineKeyboardButton(
                text="❌ Нет",
                callback_data=C.cb(C.S_PART, "set_premium", index, 0, chat_id),
            ),
        )
    kb.row(
        InlineKeyboardButton(
            text="⏭ Пропустить",
            callback_data=C.cb(C.S_PART, "skip", index, field, chat_id),
        )
    )
    return with_back(kb, C.cb(C.S_PART, "open", index, chat_id)).as_markup()


def templates_menu(premium: bool = False) -> InlineKeyboardMarkup:
    """Список шаблонов."""
    from bot.services.templates_service import templates_service

    kb = InlineKeyboardBuilder()
    for template in templates_service.available(premium):
        label = f"{template.emoji} {template.title}"
        if template.premium_only and not premium:
            label = f"🔒 {label}"
        kb.row(
            InlineKeyboardButton(
                text=label,
                callback_data=C.cb(C.S_TPL, "use", template.key),
            )
        )
    return with_back(kb, BACK_CREATE).as_markup()


def template_card(template, chat_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="✅ Создать переписку",
            callback_data=C.cb(C.S_TPL, "build", template.key),
        )
    )
    return with_back(kb, C.cb(C.S_TPL, "back")).as_markup()


__all__ = [
    "STYLE_EMOJI",
    "BACK_CREATE",
    "style_menu",
    "participants_menu",
    "participant_card",
    "participant_field_skip",
    "templates_menu",
    "template_card",
]
