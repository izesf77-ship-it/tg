"""Раздел «Мои переписки»: список, открытие, дублирование, удаление."""

from __future__ import annotations

from bot.middleware import get_services
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import screens
from bot.keyboards import common as KB
from bot.keyboards import menus as MK
from bot.keyboards import texts as T
from bot.states import Flow
from bot.utils import callbacks as C

logger = logging.getLogger(__name__)

router = Router(name="my_chats")

PAGE_SIZE = MK.PAGE_SIZE


async def open_my_chats(target, state: FSMContext, page: int = 0) -> None:
    """Показать список сохранённых переписок."""
    chats = get_services()["chats"]
    total = await chats.count_saved(target.from_user.id)
    items = await chats.list_saved(
        target.from_user.id, limit=PAGE_SIZE, offset=page * PAGE_SIZE
    )
    text = T.chats_list_text(items, total, page, PAGE_SIZE)
    keyboard = MK.chats_list(items, page, total, PAGE_SIZE)
    if isinstance(target, Message):
        await target.answer(text, parse_mode=screens.PARSE_MODE, reply_markup=keyboard)
    else:
        await screens.show(target, text, keyboard)


def _open_keyboard(chat_id: int, is_draft: bool):
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    if not is_draft:
        kb.row(
            InlineKeyboardButton(
                text="✏️ Открыть в редакторе", callback_data=C.cb(C.S_MY, "edit", chat_id)
            )
        )
    kb.row(
        InlineKeyboardButton(
            text="🖼 Сгенерировать изображение",
            callback_data=C.cb(C.S_MY, "render", chat_id),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="📋 Дублировать", callback_data=C.cb(C.S_MY, "dup", chat_id)
        ),
        InlineKeyboardButton(
            text="🗑 Удалить", callback_data=C.cb(C.S_MY, "del", chat_id)
        ),
    )
    kb.row(InlineKeyboardButton(text="⬅️ К списку", callback_data=C.cb(C.S_MY, "back_list")))
    return kb.as_markup()


@router.callback_query(F.data.startswith(C.S_MY + ":"))
async def on_my_chats(callback: CallbackQuery, state: FSMContext) -> None:
    """Действия со списком переписок."""
    action = C.action(callback.data)
    chats = get_services()["chats"]
    user_id = callback.from_user.id

    if action == "noop":
        await screens.safe_answer(callback)
        return
    if action == "back_list":
        await open_my_chats(callback, state, 0)
        return
    if action == "page":
        page = C.arg_int(callback.data, 0, 0)
        await screens.safe_answer(callback)
        await open_my_chats(callback, state, page)
        return

    if action == "cancel_del":
        # Проверка chat_id ниже: у этой кнопки его нет вовсе, и раньше
        # «↩️ Отмена» отвечала «Переписка не найдена».
        await open_my_chats(callback, state, 0)
        return

    chat_id = C.chat_id_of(callback.data)
    if chat_id < 0:
        await screens.safe_answer(
            callback, "Эта кнопка устарела. Откройте переписку заново.", alert=True
        )
        return

    if action == "open":
        chat = await chats.get_chat(user_id, chat_id)
        if chat is None:
            await screens.safe_answer(callback, "Переписка не найдена.", alert=True)
            return
        config = await chats.get_config(user_id, chat_id)
        await state.set_state(Flow.editor)
        await state.update_data(chat_id=chat_id, page=0, opened_saved=True)
        await screens.show(
            callback,
            T.chat_card(chat, config)
            + "\n\nОткрыть в редакторе или сгенерировать изображение заново?",
            _open_keyboard(chat_id, chat.is_draft),
        )
        return

    if action == "dup":
        try:
            copy = await chats.duplicate(user_id, chat_id)
        except Exception as exc:  # noqa: BLE001
            logger.info("Не удалось дублировать #%s: %s", chat_id, exc)
            await screens.safe_answer(callback, "Не удалось дублировать.", alert=True)
            return
        logger.info("Дублирование #%s -> #%s", chat_id, copy.id)
        await screens.safe_answer(callback, "📋 Переписка продублирована.")
        await open_my_chats(callback, state, 0)
        return

    if action == "del":
        chat = await chats.get_chat(user_id, chat_id)
        title = str(chat.title) if chat else f"#{chat_id}"
        await screens.show(
            callback,
            f"🗑 <b>Удалить переписку?</b>\n\n{T.esc(title)}\nДействие нельзя отменить.",
            MK.confirm_delete_chat(chat_id),
        )
        return

    if action == "del_yes":
        target_id = C.arg_int(callback.data, 0, chat_id)
        try:
            await chats.delete(user_id, target_id)
        except Exception as exc:  # noqa: BLE001
            logger.info("Не удалось удалить #%s: %s", target_id, exc)
        await state.clear()
        await screens.show(
            callback,
            "🗑 Переписка удалена.\n\n" + T.WELCOME,
            reply_markup=KB.main_menu(),
        )
        return

    if action == "edit":
        config = await chats.get_config(user_id, chat_id)
        await state.set_state(Flow.editor)
        await state.update_data(chat_id=chat_id, page=0, opened_saved=True)
        from bot.handlers.editor import show_editor

        await show_editor(
            callback, config, chat_id, state, 0,
            header="✏️ <b>Редактирование сохранённой переписки</b>",
        )
        return

    if action == "render":
        from bot.handlers.editor import _send_render
        from bot.keyboards.editor import done_keyboard

        chat = await chats.get_chat(user_id, chat_id)
        config = await chats.get_config(user_id, chat_id)
        if chat is None or not config.messages:
            await screens.safe_answer(callback, "Переписка пуста.", alert=True)
            return
        await _send_render(
            callback, state, config, chat_id, user_id,
            "✅ <b>Готово.</b>\n\n"
            "Это фиктивная переписка, созданная в конструкторе.",
            done_keyboard(chat_id),
        )
        return

    await screens.safe_answer(callback, "Неизвестное действие.", alert=True)


@router.message(F.text == KB.BTN_MY)
async def btn_my_chats(message: Message, state: FSMContext) -> None:
    await open_my_chats(message, state, 0)


__all__ = ["router", "open_my_chats", "on_my_chats"]