"""Стартовые хендлеры: /start, /help, /cancel, главное меню."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot import screens
from bot.keyboards import common as KB
from bot.keyboards import texts as T
from bot.middleware import get_services
from bot.states import Flow
from bot.utils import text_utils as TX
from bot.utils.time_utils import today_label

logger = logging.getLogger(__name__)

router = Router(name="start")

# Тексты кнопок главного меню (ReplyKeyboard)
MENU_TEXTS = {KB.BTN_CREATE, KB.BTN_MY, KB.BTN_HELP, KB.BTN_SETTINGS, KB.BTN_CANCEL}


@router.message(CommandStart(deep_link=False))
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Приветствие и предложение продолжить незавершённую переписку."""
    await state.clear()
    await message.answer(T.WELCOME, reply_markup=KB.main_menu())

    # Автосохранение: предлагаем продолжить черновик
    # Сервисы берём из middleware-данных, а НЕ из message.data:
    # у Message нет такого поля (у CallbackQuery оно занято строкой).
    chats = get_services()["chats"]
    try:
        draft = await chats.get_draft(message.from_user.id)
    except Exception as exc:  # noqa: BLE001 - черновик не должен ломать /start
        logger.warning("Не удалось получить черновик: %s", exc)
        draft = None
    if draft is not None and draft.message_count > 0:
        await message.answer(
            "📌 <b>У вас есть незавершённая переписка</b>\n\n"
            f"{TX.messages_word(draft.message_count)} · стиль {draft.style}\n\n"
            "Продолжить редактирование?",
            parse_mode=screens.PARSE_MODE,
            reply_markup=_draft_keyboard(draft.id),
        )
    else:
        await message.answer(
            "Нажмите <b>➕ Создать переписку</b>, чтобы начать.",
            parse_mode=screens.PARSE_MODE,
        )


def _draft_keyboard(chat_id: int):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    from bot.utils import callbacks as C

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="▶️ Продолжить", callback_data=C.cb(C.S_EDIT, "resume", chat_id)
        ),
        InlineKeyboardButton(
            text="🗑 Начать новую", callback_data=C.cb(C.S_EDIT, "restart")
        ),
    )
    return kb.as_markup()


@router.message(Command("help"))
@router.message(Command("how"))
async def cmd_help(message: Message) -> None:
    """Справка и правила использования."""
    await message.answer(
        T.HOW_IT_WORKS, parse_mode=screens.PARSE_MODE, reply_markup=KB.main_menu()
    )
    await message.answer(
        T.RULES, parse_mode=screens.PARSE_MODE, reply_markup=KB.main_menu()
    )


@router.message(Command("cancel"))
@router.message(F.text == KB.BTN_CANCEL)
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    """Отмена любой операции и возврат в главное меню."""
    await state.clear()
    await message.answer(
        "❌ Действие отменено.\n\n" + T.WELCOME,
        parse_mode=screens.PARSE_MODE,
        reply_markup=KB.main_menu(),
    )


@router.message(F.text == KB.BTN_HELP)
async def btn_help(message: Message) -> None:
    await cmd_help(message)


@router.message(F.text == KB.BTN_CREATE)
async def btn_create(message: Message, state: FSMContext) -> None:
    """Кнопка «Создать переписку» из главного меню."""
    from bot.handlers.create import open_creation

    await open_creation(message, state)


@router.message(F.text == KB.BTN_MY)
async def btn_my_chats(message: Message, state: FSMContext) -> None:
    """Кнопка «Мои переписки»."""
    from bot.handlers.my_chats import open_my_chats

    await open_my_chats(message, state)


@router.message(F.text == KB.BTN_SETTINGS)
async def btn_settings(message: Message, state: FSMContext) -> None:
    """Кнопка «Настройки»."""
    from bot.handlers.menus import open_settings

    await open_settings(message, state)


@router.message(Command("premium"))
async def cmd_premium(message: Message) -> None:
    """Информация о Premium (оплата пока не подключена)."""
    from bot.services.premium_service import premium_service

    await message.answer(
        T.premium_screen(premium_service.features(), premium_service.stars_price),
        parse_mode=screens.PARSE_MODE,
        reply_markup=KB.main_menu(),
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """/stats доступна только администраторам (реализация в admin.py)."""
    from bot.config import settings

    if not settings.is_admin(message.from_user.id):
        await message.answer("Команда доступна только администраторам.")
        return
    from bot.handlers.admin import send_stats

    await send_stats(message)


__all__ = ["router", "cmd_start", "cmd_help", "cmd_cancel", "MENU_TEXTS"]
