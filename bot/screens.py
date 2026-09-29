"""Хелперы для отрисовки экранов.

Главная идея — редактировать уже отправленное сообщение вместо
создания новых, чтобы в чате не накапливались десятки сообщений.
"""

from __future__ import annotations

import logging
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    Chat,
    InlineKeyboardMarkup,
    InputFile,
    Message,
    ReplyKeyboardMarkup,
)

from bot.utils.errors import BotError

logger = logging.getLogger(__name__)

PARSE_MODE = "HTML"


async def _edit_text(
    target: Message | CallbackQuery,
    text: str,
    keyboard: Optional[InlineKeyboardMarkup] = None,
    reply_markup: Optional[ReplyKeyboardMarkup] = None,
) -> None:
    """Отредактировать текст сообщения, на которое нажали кнопку."""
    if isinstance(target, CallbackQuery):
        message = target.message
    else:
        message = target
    if message is None:
        return
    try:
        await message.edit_text(
            text, parse_mode=PARSE_MODE, reply_markup=keyboard, disable_web_page_preview=True
        )
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return
        logger.debug("Не удалось отредактировать сообщение: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Ошибка редактирования сообщения: %s", exc)


async def _edit_photo(
    target: Message | CallbackQuery,
    photo: bytes,
    caption: str,
    keyboard: Optional[InlineKeyboardMarkup] = None,
    filename: str = "chat.png",
) -> None:
    """Заменить изображение в сообщении (или отправить новое)."""
    if isinstance(target, CallbackQuery):
        message = target.message
    else:
        message = target
    file = InputFile(photo, filename=filename)
    if message is not None and message.photo:
        try:
            await message.edit_media(
                media=file, caption=caption, parse_mode=PARSE_MODE, reply_markup=keyboard
            )
            return
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc).lower():
                return
            logger.debug("Не удалось заменить изображение: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Ошибка замены изображения: %s", exc)
    await send_photo(
        message.chat if message else None, photo, caption, keyboard, filename
    )


async def send_photo(
    chat: Optional[object],
    photo: bytes,
    caption: str = "",
    keyboard: Optional[InlineKeyboardMarkup] = None,
    filename: str = "chat.png",
) -> Optional[Message]:
    """Отправить изображение с подписью."""
    if chat is None:
        return None
    try:
        return await chat.send_photo(
            InputFile(photo, filename=filename),
            caption=caption[:1024],
            parse_mode=PARSE_MODE,
            reply_markup=keyboard,
        )
    except TelegramBadRequest as exc:
        logger.warning("Telegram отклонил фото: %s", exc)
        await chat.send_message("Не удалось отправить изображение: слишком большой файл.")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ошибка отправки изображения")
        try:
            await chat.send_message("Не удалось отправить изображение.")
        except Exception:  # noqa: BLE001 # pragma: no cover
            pass
    return None


async def show(
    target: Message | CallbackQuery,
    text: str,
    keyboard: Optional[InlineKeyboardMarkup] = None,
    reply_markup: Optional[ReplyKeyboardMarkup] = None,
) -> None:
    """Показать текстовый экран (edit или send)."""
    if isinstance(target, CallbackQuery):
        await target.answer()
        await _edit_text(target, text, keyboard, reply_markup)
    else:
        await target.answer(text, parse_mode=PARSE_MODE, reply_markup=reply_markup)


async def new(
    bot: Bot,
    chat_id: int,
    text: str,
    keyboard: Optional[InlineKeyboardMarkup] = None,
    reply_markup: Optional[ReplyKeyboardMarkup] = None,
) -> Optional[Message]:
    """Отправить новый текстовый экран."""
    try:
        return await bot.send_message(
            chat_id,
            text,
            parse_mode=PARSE_MODE,
            reply_markup=reply_markup or keyboard,
            disable_web_page_preview=True,
        )
    except TelegramBadRequest as exc:
        logger.warning("Telegram отклонил сообщение: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ошибка отправки сообщения")
    return None


async def preview(
    target: Message | CallbackQuery,
    photo: bytes,
    caption: str,
    keyboard: Optional[InlineKeyboardMarkup] = None,
) -> None:
    """Показать предпросмотр изображения."""
    if isinstance(target, CallbackQuery):
        await target.answer()
        await _edit_photo(target, photo, caption, keyboard)
    else:
        await _edit_photo(target, photo, caption, keyboard)


async def safe_answer(callback: CallbackQuery, text: str = "", alert: bool = False) -> None:
    """Ответить на callback, не падая при устаревшем сообщении."""
    try:
        await callback.answer(text, show_alert=alert)
    except TelegramBadRequest as exc:
        logger.debug("Callback устарел: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Ошибка ответа на callback: %s", exc)


async def notify(target: Message | CallbackQuery, text: str) -> None:
    """Отправить короткое уведомление (в ответ на действие)."""
    if isinstance(target, CallbackQuery):
        await safe_answer(target, text[:200], alert=False)
    else:
        try:
            await target.answer(text[:4000], parse_mode=PARSE_MODE)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Не удалось отправить уведомление: %s", exc)


def message_of(target: Message | CallbackQuery) -> Optional[Message]:
    """Сообщение, к которому относится событие (у CallbackQuery — ``.message``).

    У ``CallbackQuery`` поля ``.chat`` не существует вовсе, а ``.message``
    бывает ``None`` (у сообщений-подсказок в поле ввода). Раньше хендлеры
    писали ``target.chat`` напрямую — и падали с AttributeError.
    """
    if isinstance(target, CallbackQuery):
        return target.message
    return target


def chat_of(target: Message | CallbackQuery) -> Optional[Chat]:
    """Чат, в котором нужно отправить ответ (у CallbackQuery — ``message.chat``)."""
    message = message_of(target)
    return message.chat if message is not None else None


async def ask(
    target: Message | CallbackQuery,
    text: str,
    keyboard: Optional[InlineKeyboardMarkup] = None,
    reply_markup: Optional[ReplyKeyboardMarkup] = None,
) -> bool:
    """Отправить вопрос с клавиатурой ввода (безопасная замена ``X.answer``).

    Возвращает ``True``, если сообщение отправлено, и ``False`` — если
    отправлять было некуда.
    """
    message = message_of(target)
    if message is None:
        logger.debug("Некуда отправить вопрос: у события нет сообщения")
        return False
    try:
        await message.answer(
            text,
            parse_mode=PARSE_MODE,
            reply_markup=reply_markup or keyboard,
        )
        return True
    except TelegramBadRequest as exc:
        logger.warning("Telegram отклонил сообщение: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Не удалось отправить вопрос")
    return False


__all__ = [
    "PARSE_MODE",
    "show",
    "new",
    "preview",
    "send_photo",
    "safe_answer",
    "notify",
    "ask",
    "message_of",
    "chat_of",
    "BotError",
]
