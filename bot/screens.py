"""Хелперы для отрисовки экранов.

Главная идея — редактировать уже отправленное сообщение вместо
создания новых, чтобы в чате не накапливались десятки сообщений.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from pathlib import Path
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    Chat,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
)

from bot.utils.errors import BotError

logger = logging.getLogger(__name__)

PARSE_MODE = "HTML"

# Бот и чат для редкого случая: CallbackQuery без сообщения. Заполняются
# в middleware, чтобы отправка работала и там, где message == None.
_CURRENT_BOT: ContextVar[Optional[Bot]] = ContextVar(
    "screens_current_bot", default=None
)
_CURRENT_CHAT_ID: ContextVar[Optional[int]] = ContextVar(
    "screens_current_chat_id", default=None
)


async def _edit_text(
    target: Message | CallbackQuery,
    text: str,
    keyboard: Optional[InlineKeyboardMarkup] = None,
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
    file = _as_file(photo, filename)
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
    # Передаём сам Message, а не message.chat: у Chat нет метода send_photo.
    await send_photo(message, photo, caption, keyboard, filename)


async def send_photo(
    target: object,
    photo: bytes,
    caption: str = "",
    keyboard: Optional[InlineKeyboardMarkup] = None,
    filename: str = "chat.png",
) -> Optional[Message]:
    """Отправить изображение с подписью.

    Здесь было две ошибки подряд, поэтому делаю максимально устойчиво:

    1. Параметр назывался ``chat``, и туда передавался ``message.chat``.
       Но у объекта ``Chat`` в aiogram 3.31 НЕТ метода ``send_photo``::

          AttributeError: 'Chat' object has no attribute 'send_photo'

    2. У ``Message`` в aiogram 3.31 тоже нет ``send_photo`` — только
       ``answer_photo`` и ``reply_photo`` (проверено по исходникам пакета).
       Метод ``send_photo`` есть лишь у ``Bot``.

    Поэтому отправляем через ``Bot.send_photo(chat_id=...)``: это единственный
    способ, который работает для Message, CallbackQuery и Bot одинаково.

    ``photo`` приходит как ``bytes`` (так возвращает рендерер), а ``InputFile``
    требует объект с методом ``read()``. Без обёртки в ``BytesIO`` отправка
    падала бы с TypeError, поэтому она здесь.
    """
    # 1) Найти бота и чат: у Bot нет chat_id, у Message/CallbackQuery — есть.
    bot: Optional[Bot] = None
    chat_id: Optional[int] = None

    if isinstance(target, Bot):
        bot = target
    elif isinstance(target, Message):
        # У Message поле .bot заполняется контекстом aiogram при обработке
        # апдейта. Если его нет (тест, необработанный апдейт) — берём из
        # контекста события, который заполняет middleware.
        bot = target.bot or _bot_from_context()
        chat_id = target.chat.id
    elif isinstance(target, CallbackQuery):
        if target.message is not None:
            bot = target.message.bot or _bot_from_context()
            chat_id = target.message.chat.id
        else:
            # Сообщения нет — берём бота и чат из контекста события.
            bot = _bot_from_context()
            chat_id = _callback_chat_id_from_context()
    elif isinstance(target, Chat):
        # Число чатов без сообщения: отправлять нечем, но не падаем.
        bot = _bot_from_context()
        chat_id = target.id

    if bot is None or chat_id is None:
        logger.debug("Некуда отправить изображение: нет bot/chat_id")
        return None

    try:
        return await bot.send_photo(
            chat_id=chat_id,
            # InputFile в aiogram 3.31 абстрактный: для байтов нужен
            # BufferedInputFile. Создаём только здесь, когда отправка точно
            # будет выполняться.
            photo=_as_file(photo, filename),
            caption=caption[:1024],
            parse_mode=PARSE_MODE,
            reply_markup=keyboard,
        )
    except TelegramBadRequest as exc:
        logger.warning("Telegram отклонил фото: %s", exc)
        await _notify_send_failure(bot, chat_id, "Не удалось отправить изображение: слишком большой файл.")
    except Exception:  # noqa: BLE001
        logger.exception("Ошибка отправки изображения")
        await _notify_send_failure(bot, chat_id, "Не удалось отправить изображение.")
    return None


def _bot_from_context() -> Optional[Bot]:
    """Бот из контекста aiogram (для редкого случая без сообщения)."""
    try:
        return _CURRENT_BOT.get()
    except Exception:  # noqa: BLE001 # pragma: no cover
        return None


def _callback_chat_id_from_context() -> Optional[int]:
    return _CURRENT_CHAT_ID.get()


def _as_file(source: object, source_filename: str) -> object:
    """Привести изображение к объекту, который понимает aiogram.

    В aiogram 3.31 ``InputFile`` — АБСТРАКТНЫЙ класс, его нельзя создать
    напрямую (и нельзя передать ``bytes``/``BytesIO``)::

        TypeError: Can't instantiate InputFile for abstract class InputFile

    Для байтов существует отдельный класс ``BufferedInputFile(file, filename)``.
    Рендерер отдаёт ``bytes`` — значит нужен именно он.
    """
    from aiogram.types import BufferedInputFile, FSInputFile, URLInputFile

    if isinstance(source, (BufferedInputFile, FSInputFile, URLInputFile)):
        return source
    if isinstance(source, (bytes, bytearray, memoryview)):
        return BufferedInputFile(bytes(source), filename=source_filename)
    if isinstance(source, (str, Path)):
        return FSInputFile(source, filename=source_filename)
    if hasattr(source, "read"):
        return BufferedInputFile(source.read(), filename=source_filename)
    return source


async def _notify_send_failure(bot: Bot, chat_id: int, text: str) -> None:
    """Сообщить об ошибке отправки, не завалив хендлер."""
    try:
        await bot.send_message(chat_id, text)
    except Exception:  # noqa: BLE001 # pragma: no cover
        pass


def bind_event_context(bot: Optional[Bot], chat_id: Optional[int]) -> None:
    """Запомнить бота и чата текущего события.

    Нужно для отправки изображений из callback'ов без сообщения: у них
    нет ни ``.message.bot``, ни ``.message.chat.id``.
    """
    _CURRENT_BOT.set(bot)
    _CURRENT_CHAT_ID.set(chat_id)


async def show(
    target: Message | CallbackQuery,
    text: str,
    keyboard: Optional[InlineKeyboardMarkup] = None,
    reply_markup: Optional[ReplyKeyboardMarkup] = None,
) -> None:
    """Показать текстовый экран (edit или send)."""
    if isinstance(target, CallbackQuery):
        await target.answer()
        if reply_markup is not None:
            message = target.message
            if message is not None:
                try:
                    await message.edit_reply_markup(reply_markup=None)
                except TelegramBadRequest as exc:
                    logger.debug("Не удалось убрать старую клавиатуру: %s", exc)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Ошибка удаления старой клавиатуры: %s", exc)
            bot = message.bot if message is not None else _bot_from_context()
            chat_id = message.chat.id if message is not None else _callback_chat_id_from_context()
            if bot is not None and chat_id is not None:
                await new(bot, chat_id, text, reply_markup=reply_markup)
            else:
                logger.warning("Не удалось показать reply-клавиатуру: нет bot/chat")
        else:
            await _edit_text(target, text, keyboard)
    else:
        await target.answer(
            text,
            parse_mode=PARSE_MODE,
            reply_markup=reply_markup or keyboard,
        )


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
    "bind_event_context",
    "BotError",
]
