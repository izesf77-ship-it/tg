"""Экраны главного меню: настройки, лимиты, Premium, справка."""

from __future__ import annotations

import asyncio
import logging

from bot.middleware import (
    db_session,
    get_context,
    get_db_user,
    get_services,
    is_premium,
)

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import screens
from bot.config import settings as app_settings
from bot.keyboards import common as KB
from bot.keyboards import menus as MK
from bot.keyboards import texts as T
from bot.models.user import User
from bot.states import Flow
from bot.utils import callbacks as C
from bot.utils import text_utils as TX

logger = logging.getLogger(__name__)

router = Router(name="menus")


def _anonymous_user(user_id: int) -> User:
    """Несохранённый пользователь для экранов, когда БД была недоступна.

    Объект не добавляется в сессию: он нужен только чтобы отрисовать
    экран настроек, когда регистрация в БД провалилась.
    """
    return User(
        id=user_id,
        first_name="Пользователь",
        username=None,
        is_premium=False,
        is_banned=False,
        is_admin=False,
    )


async def open_settings(target, state: FSMContext) -> None:
    """Экран настроек бота."""
    user_id = target.from_user.id
    limits = get_services()["limits"]
    user = get_db_user()
    from bot.services.ai_service import ai_service

    # user бывает None, если БД была занята при регистрации: middleware
    # откатил сессию и положил None. Раньше здесь стояло user.is_premium —
    # экран настроек падал с AttributeError. Берём флаг безопасно, а сам
    # user подставляем заглушкой, чтобы T.settings_screen получил объект.
    premium = is_premium()
    if user is None:
        user = _anonymous_user(user_id)

    image_check = await limits.check_image(user_id, premium)
    ai_check = await limits.check_ai(user_id, premium)

    text = T.settings_screen(
        user,
        f"{image_check.used}/{image_check.limit or '∞'}",
        f"{ai_check.used}/{ai_check.limit or '∞'}",
        ai_service.status_text(),
    )
    keyboard = MK.global_settings_menu()
    if isinstance(target, Message):
        await target.answer(text, parse_mode=screens.PARSE_MODE, reply_markup=keyboard)
    else:
        await screens.show(target, text, keyboard)


@router.callback_query(F.data.startswith(C.S_MENU + ":"))
async def on_menu(callback: CallbackQuery, state: FSMContext) -> None:
    """Кнопки главного меню в inline-разметке."""
    action = C.action(callback.data)
    from bot.handlers.create import open_creation
    from bot.handlers.my_chats import open_my_chats

    if action == "home":
        await state.clear()
        await screens.show(callback, T.WELCOME, reply_markup=KB.main_menu())
        return

    if action == "create":
        await open_creation(callback, state)
        return

    if action == "my":
        await open_my_chats(callback, state, 0)
        return

    if action == "help":
        await screens.show(
            callback,
            T.HOW_IT_WORKS + "\n\n" + T.RULES,
            MK.help_menu(),
        )
        return

    if action == "settings":
        await open_settings(callback, state)
        return

    await screens.safe_answer(callback, "Неизвестное действие.", alert=True)


@router.callback_query(F.data.startswith(C.S_SETTINGS + ":"))
async def on_settings(callback: CallbackQuery, state: FSMContext) -> None:
    """Настройки бота."""
    action = C.action(callback.data)
    limits = get_services()["limits"]
    user_id = callback.from_user.id

    if action == "limits":
        image_check = await limits.check_image(user_id)
        ai_check = await limits.check_ai(user_id)
        await screens.show(
            callback,
            T.limits_screen(
                f"{image_check.used}/{image_check.limit or '∞'}",
                f"{ai_check.used}/{ai_check.limit or '∞'}",
            ),
            MK.global_settings_menu(),
        )
        return

    if action == "premium":
        from bot.services.premium_service import premium_service

        await screens.show(
            callback,
            T.premium_screen(premium_service.features(), premium_service.stars_price),
            MK.global_settings_menu(),
        )
        return

    if action == "wipe":
        await screens.show(
            callback,
            "🗑 <b>Удалить все мои данные?</b>\n\n"
            "Будут удалены все переписки, черновики и статистика использования.\n"
            "Действие нельзя отменить.",
            MK.confirm_wipe(),
        )
        return

    if action == "wipe_yes":
        session = db_session()
        from bot.models import Chat, UsageEvent
        from sqlalchemy import delete

        await session.execute(delete(Chat).where(Chat.user_id == user_id))
        await session.execute(delete(UsageEvent).where(UsageEvent.user_id == user_id))
        from bot.utils.files import delete_media

        await asyncio.to_thread(delete_media, user_id)
        user = get_db_user()
        if user is not None:
            user.total_images = 0
            user.total_ai = 0
            user.total_chats = 0
            user.total_actions = 0
            session.add(user)
        await session.commit()
        logger.info("Данные пользователя %s удалены", user_id)
        await state.clear()
        await screens.show(
            callback,
            "🗑 Все данные удалены.\n\n" + T.WELCOME,
            reply_markup=KB.main_menu(),
        )
        return

    await screens.safe_answer(callback, "Неизвестное действие.", alert=True)


@router.callback_query(F.data.startswith(C.S_AI + ":"))
async def on_ai_entry(callback: CallbackQuery, state: FSMContext) -> None:
    """Вход в AI-генерацию сценария."""
    await open_ai_entry(callback, state, C.action(callback.data))


async def open_ai_entry(
    target: Message | CallbackQuery,
    state: FSMContext,
    action: str = "ask",
) -> None:
    """Открыть AI-ввод из callback или кнопки главного меню."""
    from bot.services.ai_service import ai_service

    if action == "why" or not ai_service.enabled:
        await state.clear()
        if isinstance(target, CallbackQuery):
            await screens.show(target, T.HELP_AI_DISABLED, MK.ai_menu(False))
        else:
            await target.answer(
                T.HELP_AI_DISABLED,
                parse_mode=screens.PARSE_MODE,
                reply_markup=KB.main_menu(),
            )
        return

    await state.clear()
    prompt = (
        f"✨ <b>Создание сценария</b>\n\n{T.field_prompt('ai_prompt')}\n\n"
        "AI придумает <i>вымышленный</i> диалог для юмора, мемов или контента.\n\n"
        f"{T.INPUT_CANCEL_HINT}"
    )
    if isinstance(target, CallbackQuery):
        await screens.safe_answer(target)
    sent = await screens.ask(
        target,
        prompt,
        reply_markup=KB.input_menu("Опишите сценарий…"),
    )
    if sent:
        await state.set_state(Flow.ai_prompt)


@router.message(F.text == KB.BTN_SETTINGS)
async def btn_settings(message: Message, state: FSMContext) -> None:
    await open_settings(message, state)


__all__ = [
    "router",
    "open_settings",
    "open_ai_entry",
    "on_menu",
    "on_settings",
    "on_ai_entry",
]
