"""Обработка неожиданных событий: неизвестные кнопки и команды.

Эти хендлеры должны подключаться ПОСЛЕДНИМИ, чтобы перехватывать
всё, что не обработано основными роутерами.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot import screens
from bot.keyboards import common as KB
from bot.utils import callbacks as C

logger = logging.getLogger(__name__)

router = Router(name="errors")
router.message.filter(F.text)
router.callback_query.filter()


@router.callback_query()
async def unknown_callback(callback: CallbackQuery) -> None:
    """Неизвестная или устаревшая кнопка — ведём в главное меню."""
    data = callback.data or ""
    logger.info("Неизвестный callback: %r (user=%s)", data, callback.from_user.id)
    await screens.safe_answer(callback, "Кнопка устарела. Открываю меню…")
    if data == C.cb(C.S_EDIT, "noop") or data == C.cb(C.S_MY, "noop"):
        return
    try:
        if callback.message:
            await callback.message.edit_text(
                KB.MAIN_MENU_TEXT,
                parse_mode=screens.PARSE_MODE,
                reply_markup=None,
            )
            await callback.message.answer(
                KB.MAIN_MENU_TEXT,
                parse_mode=screens.PARSE_MODE,
                reply_markup=KB.main_menu(),
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Не удалось показать меню после неизвестной кнопки: %s", exc)


@router.message()
async def unknown_command(message: Message) -> None:
    """Неизвестная команда или текст вне режима ввода."""
    text = (message.text or "").strip()
    if text.startswith("/"):
        command = text.split()[0].split("@")[0]
        logger.info("Неизвестная команда %s (user=%s)", command, message.from_user.id)
        await message.answer(
            "Такой команды нет. Вот что можно сделать:",
            reply_markup=KB.main_menu(),
        )
    else:
        await message.answer(
            "Я не понял, что вы хотите сделать. Выберите действие в меню 👇",
            reply_markup=KB.main_menu(),
        )


__all__ = ["router", "unknown_callback", "unknown_command"]
