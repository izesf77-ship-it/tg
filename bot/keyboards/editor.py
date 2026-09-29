"""Клавиатуры редактора сообщений."""

from __future__ import annotations

from typing import List, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboards.common import with_back
from bot.schemas import ChatConfig, Message
from bot.utils import callbacks as C

BACK_EDITOR = C.cb(C.S_EDIT, "home")


def back_to_list(chat_id: int) -> str:
    """Кнопка «Назад» из вложенных экранов редактора → список сообщений.

    Раньше здесь стоял ``ed:back:<chat_id>``, а хендлер на ``back``
    открывал экран УЧАСТНИКОВ. Из-за этого «Назад» из меню времени,
    реакций, медиа и из предпросмотра уводил в сторону, а данные
    правки терялись из виду.
    """
    return C.cb(C.S_EDIT, "list", chat_id)

MESSAGE_ICONS = {
    "text": "💬", "image": "🖼", "voice": "🎤", "file": "📎",
    "sticker": "🩻", "service": "ℹ️", "date": "📅", "forward": "↪",
}


def message_label(
    config: ChatConfig,
    message: Message,
    index: int,
    author_labels: Optional[List[str]] = None,
) -> str:
    """Подпись кнопки со списком сообщений."""
    icon = MESSAGE_ICONS.get(message.kind.value, "💬")
    if author_labels and 0 <= message.author_index < len(author_labels):
        author = author_labels[message.author_index]
    else:
        author = "Участник"
    marks = []
    if message.reply_to:
        marks.append("↩️")
    if message.reaction:
        marks.append(message.reaction.emoji)
    if message.kind.value == "forward" and message.forward_from:
        marks.append(f"от {message.forward_from[:12]}")
    suffix = (" " + "".join(marks)) if marks else ""
    text = message.preview(40) or message.type_icon()
    return f"{index + 1}. {icon} {author}: {text}{suffix}"


def editor_keyboard(
    config: ChatConfig,
    chat_id: int,
    page: int = 0,
    per_page: int = 8,
    author_labels: Optional[List[str]] = None,
) -> InlineKeyboardMarkup:
    """Основная клавиатура редактора со списком сообщений."""
    kb = InlineKeyboardBuilder()
    messages = config.messages
    total = len(messages)

    if total:
        start = page * per_page
        end = min(total, start + per_page)
        for index in range(start, end):
            kb.row(
                InlineKeyboardButton(
                    text=message_label(config, messages[index], index, author_labels),
                    callback_data=C.cb(C.S_EDIT, "open", index, chat_id),
                )
            )
        pages = (total + per_page - 1) // per_page
        if pages > 1:
            nav = []
            if page > 0:
                nav.append(
                    InlineKeyboardButton(
                        text="◀️",
                        callback_data=C.cb(C.S_EDIT, "page", page - 1, chat_id),
                    )
                )
            nav.append(
                InlineKeyboardButton(
                    text=f"{page + 1}/{pages}", callback_data=C.cb(C.S_EDIT, "noop")
                )
            )
            if page + 1 < pages:
                nav.append(
                    InlineKeyboardButton(
                        text="▶️",
                        callback_data=C.cb(C.S_EDIT, "page", page + 1, chat_id),
                    )
                )
            kb.row(*nav)
    else:
        kb.row(
            InlineKeyboardButton(
                text="➕ Сообщение 1",
                callback_data=C.cb(C.S_EDIT, "add", 0, chat_id),
            ),
            InlineKeyboardButton(
                text="➕ Сообщение 2",
                callback_data=C.cb(C.S_EDIT, "add", 1, chat_id),
            ),
        )

    if total:
        kb.row(
            InlineKeyboardButton(
                text="➕ Сообщение", callback_data=C.cb(C.S_EDIT, "addmenu", chat_id)
            )
        )
    kb.row(
        InlineKeyboardButton(text="👤 Участники", callback_data=C.cb(C.S_EDIT, "participants", chat_id)),
        InlineKeyboardButton(text="⚙️ Настройки", callback_data=C.cb(C.S_EDIT, "settings", chat_id)),
    )
    kb.row(
        InlineKeyboardButton(text="👀 Предпросмотр", callback_data=C.cb(C.S_EDIT, "preview", chat_id)),
        InlineKeyboardButton(text="✅ Готово", callback_data=C.cb(C.S_EDIT, "done", chat_id)),
    )
    return with_back(kb, back_to_list(chat_id)).as_markup()


def message_actions_menu(index: int, chat_id: int, config: ChatConfig) -> InlineKeyboardMarkup:
    """Действия с конкретным сообщением."""
    kb = InlineKeyboardBuilder()
    if not (0 <= index < len(config.messages)):
        return with_back(kb, C.cb(C.S_EDIT, "back", chat_id)).as_markup()

    kb.row(
        InlineKeyboardButton(
            text="✏️ Изменить", callback_data=C.cb(C.S_EDIT, "edit", index, chat_id)
        ),
        InlineKeyboardButton(
            text="🕐 Время", callback_data=C.cb(C.S_EDIT, "time", index, chat_id)
        ),
    )
    kb.row(
        InlineKeyboardButton(
            text="👤 Автор", callback_data=C.cb(C.S_EDIT, "author", index, chat_id)
        ),
        InlineKeyboardButton(
            text="🙂 Реакция", callback_data=C.cb(C.S_EDIT, "react", index, chat_id)
        ),
    )
    kb.row(
        InlineKeyboardButton(
            text="🧩 Тип", callback_data=C.cb(C.S_EDIT, "type", index, chat_id)
        ),
        InlineKeyboardButton(
            text="🖼 Медиа", callback_data=C.cb(C.S_EDIT, "media", index, chat_id)
        ),
    )
    kb.row(
        InlineKeyboardButton(
            text="⬆️ Выше", callback_data=C.cb(C.S_EDIT, "up", index, chat_id)
        ),
        InlineKeyboardButton(
            text="⬇️ Ниже", callback_data=C.cb(C.S_EDIT, "down", index, chat_id)
        ),
    )
    kb.row(
        InlineKeyboardButton(
            text="🗑 Удалить", callback_data=C.cb(C.S_EDIT, "del", index, chat_id)
        )
    )
    return with_back(kb, back_to_list(chat_id)).as_markup()


def add_message_menu(chat_id: int) -> InlineKeyboardMarkup:
    """Выбор типа добавляемого сообщения."""
    kb = InlineKeyboardBuilder()
    options = [
        ("text", "💬 Текстовое"),
        ("image", "🖼 Фотография"),
        ("voice", "🎤 Голосовое"),
        ("file", "📎 Файл"),
        ("sticker", "🩻 Стикер"),
        ("forward", "↪ Пересланное"),
        ("service", "ℹ️ Системное"),
        ("date", "📅 Разделитель дат"),
    ]
    for key, label in options:
        kb.row(
            InlineKeyboardButton(
                text=label, callback_data=C.cb(C.S_EDIT, "new", key, chat_id)
            )
        )
    return with_back(kb, back_to_list(chat_id)).as_markup()


def author_menu(
    chat_id: int,
    author_labels: List[str],
    action: str = "new",
    index: int = -1,
) -> InlineKeyboardMarkup:
    """Выбор отправителя сообщения.

    Формат кнопки: ``ed:pickauthor:<i>:<action>:<index>:<chat_id>``.
    ``chat_id`` обязателен в конце, ``index`` — предпоследний, поэтому
    ``C.chat_id_of`` / ``C.index_of`` читают их одинаково для всех кнопок.
    """
    kb = InlineKeyboardBuilder()
    for i, label in enumerate(author_labels):
        kb.row(
            InlineKeyboardButton(
                text=f"👤 {label}",
                callback_data=C.cb(C.S_EDIT, "pickauthor", i, action, index, chat_id),
            )
        )
    return with_back(kb, back_to_list(chat_id)).as_markup()


def time_menu(chat_id: int, index: int = -1) -> InlineKeyboardMarkup:
    """Выбор времени сообщения.

    Формат кнопок: ``ed:settime:now:<index>:<chat_id>`` и
    ``ed:manualtime:<index>:<chat_id>``.

    Раньше здесь стояло ``settime:now:<chat_id>:<index>`` — ``chat_id``
    оказывался НЕ последним, и ``C.chat_id_of`` возвращал индекс
    сообщения. Пользователь получал «Переписка не найдена» ровно в тот
    момент, когда устанавливал время.
    """
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="🕐 Текущее время",
            callback_data=C.cb(C.S_EDIT, "settime", "now", index, chat_id),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="⌨️ Указать вручную",
            callback_data=C.cb(C.S_EDIT, "manualtime", index, chat_id),
        )
    )
    return with_back(kb, back_to_list(chat_id)).as_markup()


def reaction_menu(index: int, chat_id: int) -> InlineKeyboardMarkup:
    """Выбор реакции: ``ed:setreact:<emoji>:<index>:<chat_id>``."""
    kb = InlineKeyboardBuilder()
    emojis = ["👍", "❤️", "😂", "🔥", "😮", "😢", "🎉", "🙏", "👀", "🤔"]
    for i in range(0, len(emojis), 5):
        kb.row(
            *[
                InlineKeyboardButton(
                    text=emoji,
                    callback_data=C.cb(C.S_EDIT, "setreact", emoji, index, chat_id),
                )
                for emoji in emojis[i : i + 5]
            ]
        )
    kb.row(
        InlineKeyboardButton(
            text="🗑 Убрать реакцию",
            callback_data=C.cb(C.S_EDIT, "setreact", "-", index, chat_id),
        )
    )
    return with_back(kb, back_to_list(chat_id)).as_markup()


def type_menu(index: int, chat_id: int) -> InlineKeyboardMarkup:
    """Смена типа сообщения: ``ed:settype:<key>:<index>:<chat_id>``."""
    kb = InlineKeyboardBuilder()
    options = [
        ("text", "💬 Текст"),
        ("image", "🖼 Фото"),
        ("voice", "🎤 Голосовое"),
        ("file", "📎 Файл"),
        ("sticker", "🩻 Стикер"),
        ("forward", "↪ Пересылка"),
        ("service", "ℹ️ Системное"),
    ]
    for key, label in options:
        kb.row(
            InlineKeyboardButton(
                text=label, callback_data=C.cb(C.S_EDIT, "settype", key, index, chat_id)
            )
        )
    return with_back(kb, back_to_list(chat_id)).as_markup()


def media_menu(index: int, chat_id: int) -> InlineKeyboardMarkup:
    """Замена медиа у сообщения."""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="📷 Прислать фото из Telegram",
            callback_data=C.cb(C.S_EDIT, "photo", index, chat_id),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="🎲 Случайное фото",
            callback_data=C.cb(C.S_EDIT, "randphoto", index, chat_id),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="🗑 Убрать медиа",
            callback_data=C.cb(C.S_EDIT, "nomedia", index, chat_id),
        )
    )
    return with_back(kb, back_to_list(chat_id)).as_markup()


def reply_target_menu(config: ChatConfig, chat_id: int) -> InlineKeyboardMarkup:
    """Выбор сообщения для ответа."""
    kb = InlineKeyboardBuilder()
    start = max(0, len(config.messages) - 10)
    for index in range(start, len(config.messages)):
        kb.row(
            InlineKeyboardButton(
                text=message_label(config, config.messages[index], index)[:50],
                callback_data=C.cb(C.S_EDIT, "replytarget", index, chat_id),
            )
        )
    return with_back(kb, back_to_list(chat_id)).as_markup()


def preview_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Клавиатура под предпросмотром."""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="✏️ Редактировать", callback_data=back_to_list(chat_id)
        ),
        InlineKeyboardButton(
            text="➕ Добавить сообщение",
            callback_data=C.cb(C.S_EDIT, "addmenu", chat_id),
        ),
    )
    kb.row(
        InlineKeyboardButton(
            text="⚙️ Настройки", callback_data=C.cb(C.S_EDIT, "settings", chat_id)
        ),
        InlineKeyboardButton(
            text="✅ Завершить", callback_data=C.cb(C.S_EDIT, "done", chat_id)
        ),
    )
    return with_back(kb, back_to_list(chat_id)).as_markup()


def done_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Клавиатура под готовым изображением."""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="🔄 Изменить", callback_data=C.cb(C.S_EDIT, "open_done", chat_id)
        ),
        InlineKeyboardButton(
            text="📂 Сохранить", callback_data=C.cb(C.S_EDIT, "save", chat_id)
        ),
        InlineKeyboardButton(
            text="🗑 Удалить", callback_data=C.cb(C.S_EDIT, "drop", chat_id)
        ),
    )
    kb.row(
        InlineKeyboardButton(text="⬅️ В меню", callback_data=C.cb(C.S_MENU, "home"))
    )
    return kb.as_markup()


__all__ = [
    "BACK_EDITOR",
    "back_to_list",
    "MESSAGE_ICONS",
    "message_label",
    "editor_keyboard",
    "message_actions_menu",
    "add_message_menu",
    "author_menu",
    "time_menu",
    "reaction_menu",
    "type_menu",
    "media_menu",
    "reply_target_menu",
    "preview_keyboard",
    "done_keyboard",
]