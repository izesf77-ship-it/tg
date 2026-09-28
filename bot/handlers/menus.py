"""Экраны главного меню: настройки, лимиты, Premium, справка."""

from __future__ import annotations

from bot.middleware import get_services, get_db_user, get_context
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import screens
from bot.config import settings as app_settings
from bot.keyboards import common as KB
from bot.keyboards import menus as MK
from bot.keyboards import texts as T
from bot.states import Flow
from bot.utils import callbacks as C
from bot.utils import text_utils as TX

logger = logging.getLogger(__name__)

router = Router(name="menus")


async def open_settings(target, state: FSMContext) -> None:
    """Экран настроек бота."""
    limits = get_services()["limits"]
    user = get_db_user()
    db_user = get_services()["user"]
    from bot.services.ai_service import ai_service

    user_id = target.from_user.id
    image_check = await limits.check_image(user_id, bool(user.is_premium))
    ai_check = await limits.check_ai(user_id, bool(user.is_premium))
    _ = db_user

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
    from bot.services.ai_service import ai_service

    action = C.action(callback.data)
    if action == "why":
        await screens.show(callback, T.HELP_AI_DISABLED, MK.ai_menu(False))
        return

    if not ai_service.enabled:
        await screens.show(callback, T.HELP_AI_DISABLED, MK.ai_menu(False))
        return

    await state.set_state(Flow.ai_prompt)
    await callback.message.answer(
        f"✨ <b>Создание сценария</b>\n\n{T.field_prompt('ai_prompt')}\n\n"
        "AI придумает <i>вымышленный</i> диалог для юмора, мемов или контента.\n\n"
        f"{T.INPUT_CANCEL_HINT}",
        parse_mode=screens.PARSE_MODE,
        reply_markup=KB.input_menu("Опишите сценарий…"),
    )


@router.message(F.text == KB.BTN_SETTINGS)
async def btn_settings(message: Message, state: FSMContext) -> None:
    await open_settings(message, state)


__all__ = ["router", "open_settings", "on_menu", "on_settings", "on_ai_entry"]
