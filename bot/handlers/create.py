"""Создание переписки: выбор стиля, настройка участников, шаблоны."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import screens
from bot.keyboards import common as KB
from bot.keyboards import create as CK
from bot.keyboards import texts as T
from bot.middleware import get_services, get_db_user
from bot.services.chat_service import ChatService
from bot.states import Flow
from bot.utils import callbacks as C
from bot.utils import files as FILES
from bot.utils import text_utils as TX
from bot.utils.errors import TextTooLongError, ValidationError
from bot.utils.time_utils import current_time_str

logger = logging.getLogger(__name__)

router = Router(name="create")

# Поля участника, вводимые текстом
PARTICIPANT_FIELDS = {"name", "username", "display_name", "status", "last_seen"}


async def open_creation(message: Message, state: FSMContext) -> None:
    """Шаг 1: выбор стиля интерфейса (или восстановление черновика)."""
    chats = get_services()["chats"]
    limits = get_services()["limits"]
    db_user = get_db_user()

    # Если уже есть черновик — предлагаем продолжить
    draft = await chats.get_draft(message.from_user.id)
    if draft is not None and draft.message_count > 0:
        await message.answer(
            "📌 У вас есть незавершённая переписка "
            f"({draft.message_count} сообщ.).\n\nПродолжить её?",
            parse_mode=screens.PARSE_MODE,
            reply_markup=_resume_keyboard(draft.id),
        )
        await state.clear()
        return

    count = await chats.count_saved(message.from_user.id)
    premium = bool(getattr(db_user, "is_premium", False))
    max_chats = limits.max_chats(premium)
    if count >= max_chats:
        await message.answer(
            f"Достигнут лимит: {max_chats} сохранённых переписок.\n"
            "Удалите лишние в разделе «📂 Мои переписки».",
            reply_markup=KB.main_menu(),
        )
        return

    await state.set_state(Flow.style)
    await message.answer(
        "🎨 <b>Выбери стиль интерфейса</b>\n\n"
        "От него зависит, как будет выглядеть итоговое изображение.\n"
        "Основной и самый проработанный стиль — Telegram.",
        parse_mode=screens.PARSE_MODE,
        reply_markup=CK.style_menu(premium),
    )


def _resume_keyboard(chat_id: int):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="▶️ Продолжить", callback_data=C.cb(C.S_EDIT, "resume", chat_id)
        ),
        InlineKeyboardButton(
            text="🗑 Начать новую", callback_data=C.cb(C.S_EDIT, "restart")
        ),
    )
    kb.row(InlineKeyboardButton(text="⬅️ В меню", callback_data=C.cb(C.S_MENU, "home")))
    return kb.as_markup()


@router.callback_query(F.data.startswith(C.S_STYLE + ":"))
async def on_style(callback: CallbackQuery, state: FSMContext) -> None:
    """Шаг 1 → 2: сохраняем стиль и создаём черновик переписки."""
    action = C.action(callback.data)
    if action == "back":
        await screens.show(callback, T.WELCOME, reply_markup=KB.main_menu())
        await state.clear()
        return

    style = C.arg(callback.data, 0)
    definition = _style_def(style)
    if definition is None:
        await screens.safe_answer(callback, "Неизвестный стиль.", alert=True)
        return
    premium = _premium_of(callback)

    if definition.get("premium_only") and not premium:
        await screens.safe_answer(
            callback, "Этот стиль доступен в Premium.", alert=True
        )
        return

    chats = get_services()["chats"]
    users = get_services()["user"]
    try:
        chat, config = await chats.create(callback.from_user.id, style=style)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Не удалось создать переписку")
        await screens.safe_answer(callback, "Не удалось создать переписку.", alert=True)
        return

    await users.count_chat(callback.from_user.id)
    await state.set_state(Flow.participants)
    await state.update_data(chat_id=chat.id, page=0)
    await screens.show(
        callback,
        T.participants_screen(config),
        CK.participants_menu(config, chat.id),
    )


def _style_def(style: str) -> Optional[dict]:
    from bot.generators import AVAILABLE_STYLES

    for definition in AVAILABLE_STYLES:
        if definition.key == style:
            return {
                "key": definition.key,
                "premium_only": definition.premium_only,
            }
    return None


def _premium_of(callback: CallbackQuery) -> bool:
    """Premium-статус пользователя из данных сессии (безопасно)."""
    db_user = get_db_user()
    return bool(getattr(db_user, "is_premium", False))


# --- Участники --------------------------------------------------------
@router.callback_query(F.data.startswith(C.S_PART + ":"))
async def on_participant(callback: CallbackQuery, state: FSMContext) -> None:
    """Навигация по участникам и изменение их полей."""
    action = C.action(callback.data)
    chats = get_services()["chats"]
    user_id = callback.from_user.id
    chat_id = C.chat_id_of(callback.data)

    if action == "next":
        if chat_id < 0:
            await screens.safe_answer(callback, "Переписка не найдена.", alert=True)
            return
        config = await chats.get_config(user_id, chat_id)
        await state.set_state(Flow.editor)
        await state.update_data(chat_id=chat_id, page=0)
        from bot.handlers.editor import show_editor

        await show_editor(callback, config, chat_id, state, 0)
        return

    if action == "back":
        await state.set_state(Flow.style)
        premium = _premium_of(callback)
        await screens.show(
            callback,
            "🎨 <b>Выбери стиль интерфейса</b>",
            CK.style_menu(premium),
        )
        return

    if action == "open":
        index = C.arg_int(callback.data, 0)
        config = await chats.get_config(user_id, chat_id)
        participant = ChatService.participant(config, index)
        if participant is None:
            await screens.safe_answer(callback, "Участник не найден.", alert=True)
            return
        await state.set_state(Flow.participant)
        await state.update_data(chat_id=chat_id, participant_index=index)
        await screens.show(
            callback,
            T.participant_screen(index, participant),
            CK.participant_card(index, participant, chat_id),
        )
        return

    if action == "field":
        index = C.arg_int(callback.data, 0)
        field = C.arg(callback.data, 1)
        config = await chats.get_config(user_id, chat_id)
        participant = ChatService.participant(config, index)
        if participant is None:
            await screens.safe_answer(callback, "Участник не найден.", alert=True)
            return

        if field == "premium":
            participant.premium = not participant.premium
            await chats.save(user_id, chat_id, config)
            await screens.show(
                callback,
                T.participant_screen(index, participant),
                CK.participant_card(index, participant, chat_id),
            )
            return

        if field == "avatar":
            await state.set_state(Flow.participant_input)
            await state.update_data(
                chat_id=chat_id, participant_index=index, field=field
            )
            await screens.show(
                callback,
                T.field_prompt("avatar") + "\n\n" + T.INPUT_CANCEL_HINT,
                CK.participant_field_skip(field, index, chat_id),
                reply_markup=KB.input_menu("Отправьте фото…"),
            )
            return

        await state.set_state(Flow.participant_input)
        await state.update_data(chat_id=chat_id, participant_index=index, field=field)
        await screens.show(
            callback,
            T.field_prompt(field) + "\n\n" + T.INPUT_CANCEL_HINT,
            CK.participant_field_skip(field, index, chat_id),
            reply_markup=KB.input_menu("Введите значение…"),
        )
        return

    if action == "skip":
        index = C.arg_int(callback.data, 0)
        field = C.arg(callback.data, 1)
        config = await chats.get_config(user_id, chat_id)
        participant = ChatService.participant(config, index)
        if participant is not None:
            if field == "name" and not participant.name:
                participant.name = f"Участник {index + 1}"
            if field == "avatar":
                participant.avatar_path = None
            await chats.save(user_id, chat_id, config)
        await screens.show(
            callback,
            T.participant_screen(index, participant) if participant else "Участник удалён",
            CK.participant_card(index, participant, chat_id) if participant else None,
        )
        return

    if action == "reset":
        index = C.arg_int(callback.data, 0)
        config = await chats.get_config(user_id, chat_id)
        from bot.schemas import Participant

        if 0 <= index < len(config.participants):
            config.participants[index] = Participant(
                name=f"Участник {index + 1}", side=index % 2, status="в сети"
            )
            await chats.save(user_id, chat_id, config)
        participant = ChatService.participant(config, index)
        await screens.show(
            callback,
            T.participant_screen(index, participant),
            CK.participant_card(index, participant, chat_id),
        )
        return

    await screens.safe_answer(callback, "Неизвестное действие.", alert=True)


# --- Ввод полей участника --------------------------------------------
@router.message(Flow.participant_input, F.photo)
async def on_participant_photo(
    message: Message, state: FSMContext, bot: Bot
) -> None:
    """Фотография участника, отправленная прямо из Telegram."""
    data = await state.get_data()
    from bot.handlers.editor import _state_chat_id

    chat_id = await _state_chat_id(data, message.from_user.id)
    index = int(data.get("participant_index", 0))
    chats = get_services()["chats"]
    config = await chats.get_config(message.from_user.id, chat_id)
    participant = ChatService.participant(config, index)
    if participant is None:
        await message.answer("Участник не найден.", reply_markup=KB.main_menu())
        await state.clear()
        return

    photo = message.photo[-1]
    path = await _download_photo(bot, photo.file_id, message.from_user.id)
    if path is None:
        await message.answer(
            "Не удалось загрузить фото. Попробуйте другое изображение.",
            reply_markup=KB.main_menu(),
        )
        return
    participant.avatar_path = str(path)
    await chats.save(message.from_user.id, chat_id, config)
    await state.set_state(Flow.participant)
    await message.answer(
        T.participant_screen(index, participant),
        parse_mode=screens.PARSE_MODE,
        reply_markup=CK.participant_card(index, participant, chat_id),
    )


async def _download_photo(bot: Bot, file_id: str, user_id: int) -> Optional[Path]:
    """Скачать фото из Telegram и сохранить на диск."""
    try:
        buffer = await bot.download(file_id)
        data = buffer.read() if hasattr(buffer, "read") else bytes(buffer)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Не удалось скачать фото: %s", exc)
        return None
    if not FILES.is_image_bytes(data):
        logger.warning("Полученный файл не является изображением")
        return None
    return FILES.save_bytes(data, user_id, ".jpg")


@router.message(Flow.participant_input, F.text)
async def on_participant_text(message: Message, state: FSMContext) -> None:
    """Текстовое поле участника."""
    data = await state.get_data()
    from bot.handlers.editor import _state_chat_id

    chat_id = await _state_chat_id(data, message.from_user.id)
    index = int(data.get("participant_index", 0))
    field = str(data.get("field", "name"))
    value = TX.clean(message.text or "")

    chats = get_services()["chats"]
    config = await chats.get_config(message.from_user.id, chat_id)
    participant = ChatService.participant(config, index)
    if participant is None:
        await message.answer("Участник не найден.", reply_markup=KB.main_menu())
        await state.clear()
        return

    if not value:
        await message.answer("Значение не может быть пустым. Попробуйте ещё раз.")
        return

    try:
        if field == "name":
            participant.name = TX.clamp(value, TX.MAX_NAME_LENGTH)
        elif field == "username":
            participant.username = TX.ensure_username(value)
            if not participant.username:
                await message.answer(
                    "Username может содержать только латинские буквы, цифры и _."
                )
                return
        elif field == "display_name":
            participant.display_name = TX.clamp(value, TX.MAX_NAME_LENGTH)
        elif field == "status":
            participant.status = TX.clamp(value, TX.MAX_STATUS_LENGTH)
        elif field == "last_seen":
            from bot.utils.time_utils import parse_time

            try:
                participant.last_seen = parse_time(value)
                participant.status = "был(а) недавно"
            except Exception:  # noqa: BLE001
                await message.answer(
                    "Неверное время. Формат: <code>12:41</code> (часы от 0 до 23)."
                )
                return
        else:
            await message.answer("Неизвестное поле.", reply_markup=KB.main_menu())
            await state.clear()
            return
    except TextTooLongError as exc:
        await message.answer(exc.user_message)
        return
    except ValidationError as exc:
        await message.answer(exc.user_message)
        return

    await chats.save(message.from_user.id, chat_id, config)
    await state.set_state(Flow.participant)
    await message.answer(
        T.participant_screen(index, participant),
        parse_mode=screens.PARSE_MODE,
        reply_markup=CK.participant_card(index, participant, chat_id),
    )


# --- Шаблоны ----------------------------------------------------------
@router.callback_query(F.data.startswith(C.S_TPL + ":"))
async def on_template(callback: CallbackQuery, state: FSMContext) -> None:
    """Показ и применение готовых шаблонов."""
    action = C.action(callback.data)
    from bot.services.templates_service import templates_service

    if action == "back":
        await state.clear()
        await screens.show(callback, T.WELCOME, reply_markup=KB.main_menu())
        return

    premium = _premium_of(callback)
    if action == "list":
        await screens.show(
            callback,
            "🎬 <b>Готовые шаблоны</b>\n\n"
            "Каждый шаблон — демонстрационная вымышленная переписка "
            "для юмора, мемов и контента.\n"
            "Выберите, чтобы посмотреть описание.",
            CK.templates_menu(premium),
        )
        return

    key = C.arg(callback.data, 0)
    template = templates_service.get(key)
    if template is None:
        await screens.safe_answer(callback, "Шаблон не найден.", alert=True)
        return

    if action == "use":
        await screens.show(callback, T.template_card(template), CK.template_card(template, -1))
        return

    if action == "build":
        if template.premium_only and not premium:
            await screens.safe_answer(
                callback, "Шаблон доступен в Premium.", alert=True
            )
            return
        chats = get_services()["chats"]
        users = get_services()["user"]
        config = template.build()
        chat, _ = await chats.create(
            callback.from_user.id, style=config.style, template=key, is_draft=True
        )
        await chats.save(callback.from_user.id, chat.id, config)
        await users.count_chat(callback.from_user.id)
        await state.set_state(Flow.editor)
        await state.update_data(chat_id=chat.id, page=0)

        from bot.handlers.editor import show_editor

        await show_editor(callback, config, chat.id, state, 0, header=(
            f"{template.emoji} <b>Шаблон «{template.title}» загружен</b>\n"
            "Это вымышленная переписка. Отредактируйте под свой сюжет."
        ))
        return

    await screens.safe_answer(callback, "Неизвестное действие.", alert=True)


# --- Возобновление и удаление черновика -------------------------------
@router.callback_query(F.data.startswith(C.S_EDIT + ":resume"))
async def on_resume(callback: CallbackQuery, state: FSMContext) -> None:
    """Продолжить незавершённую переписку."""
    chat_id = C.chat_id_of(callback.data)
    chats = get_services()["chats"]
    config = await chats.get_config(callback.from_user.id, chat_id)
    await state.set_state(Flow.editor)
    await state.update_data(chat_id=chat_id, page=0)
    from bot.handlers.editor import show_editor

    await show_editor(
        callback, config, chat_id, state, 0,
        header="▶️ <b>Продолжаем редактирование</b>",
    )


@router.callback_query(F.data.startswith(C.S_EDIT + ":restart"))
async def on_restart(callback: CallbackQuery, state: FSMContext) -> None:
    """Удалить черновик и начать новую переписку."""
    chats = get_services()["chats"]
    await chats.clear_drafts(callback.from_user.id)
    await state.set_state(Flow.style)
    premium = _premium_of(callback)
    await screens.show(
        callback,
        "🎨 <b>Выбери стиль интерфейса</b>\n\n"
        "Старый черновик удалён. Начинаем с чистого листа.",
        CK.style_menu(premium),
    )


__all__ = [
    "router",
    "open_creation",
    "on_style",
    "on_participant",
    "on_participant_text",
    "on_participant_photo",
    "on_template",
    "on_resume",
    "on_restart",
]
