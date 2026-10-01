"""Редактор сообщений: добавление, изменение, порядок, время, предпросмотр."""

from __future__ import annotations

import logging
from typing import Optional

from aiogram import Bot, F, Router
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import screens
from bot.keyboards import common as KB
from bot.keyboards import create as CK
from bot.keyboards import editor as EK
from bot.keyboards import texts as T
from bot.schemas import Message as Msg
from bot.schemas import MessageKind
from bot.middleware import get_services, get_db_user, is_premium
from bot.services.chat_service import ChatService
from bot.services.render_service import render_service
from bot.states import Flow
from bot.utils import callbacks as C
from bot.utils import text_utils as TX
from bot.utils.errors import (
    ChatNotFoundError,
    InvalidTimeError,
    LimitExceededError,
    NoMessagesError,
)
from bot.utils.time_utils import current_time_str, parse_time

logger = logging.getLogger(__name__)

router = Router(name="editor")

PER_PAGE = 8

# Медиа-параметры по умолчанию для mock-элементов
VOICE_DURATIONS = ["0:05", "0:12", "0:34", "1:02"]
FILE_NAMES = ["документ.pdf", "счёт.pdf", "фото.jpg", "заметки.txt", "презентация.pptx"]
FILE_SIZES = ["1,2 МБ", "2,4 МБ", "540 КБ", "3,1 МБ", "8,7 МБ"]
STICKER_EMOJI = ["😂", "😎", "❤️", "👍", "🔥", "😭", "🙏", "🤔"]


def pages_of(total: int, per_page: int = PER_PAGE) -> int:
    return max(1, (total + per_page - 1) // per_page)


async def show_editor(
    target,
    config,
    chat_id: int,
    state: FSMContext,
    page: int = 0,
    header: str = "",
    edit: bool = True,
) -> None:
    """Показать экран редактора (список сообщений + кнопки)."""
    total = len(config.messages)
    page = max(0, min(page, pages_of(total) - 1))
    text = T.editor_screen(config, page, pages_of(total))
    if header:
        text = f"{header}\n\n{text}"
    keyboard = EK.editor_keyboard(
        config, chat_id, page, PER_PAGE, T.author_labels(config)
    )
    if edit:
        await screens.show(target, text, keyboard)
    else:
        # Раньше здесь стояло ``target.message.bot`` / ``target.chat.id`` —
        # у CallbackQuery поля .chat нет, и ветка падала бы при None.
        chat = screens.chat_of(target)
        bot = target.bot if isinstance(target, Message) else (
            target.message.bot if target.message else None
        )
        if chat is not None and bot is not None:
            await screens.new(bot, chat.id, text, keyboard)
        else:
            await screens.show(target, text, keyboard)
    await state.update_data(page=page)


async def _state_chat_id(data: dict, user_id: int) -> int:
    """ID переписки из состояния FSM.

    Состояние хранится в памяти и теряется при перезапуске бота. Раньше
    обработчики ввода текста и времени брали ID только оттуда и выдавали
    «Переписка не найдена». Теперь при потере состояния ID восстанавливается
    по последнему черновику пользователя из БД.
    """
    chat_id = int(data.get("chat_id", -1) or -1)
    if chat_id >= 0:
        return chat_id
    draft = await get_services()["chats"].get_draft(user_id)
    return int(draft.id) if draft is not None else -1


def _event_of(target):
    """Объект события (Message или CallbackQuery) с данными пользователя.

    Раньше здесь стояло ``target if hasattr(target, "data") else target.message``:
    у Message поля data нет (всегда False), у CallbackQuery оно есть, но это
    строка callback-данных. Ветка выбиралась неверно, и для сообщений
    падало AttributeError.
    """
    if isinstance(target, CallbackQuery):
        return target
    return target


async def _resolve_chat_id(target, state: FSMContext, chats) -> int:
    """Определить ID переписки.

    Порядок: состояние FSM → callback_data → последний черновик в БД.
    Раньше был только первый вариант, поэтому после перезапуска бота
    (состояние хранится в памяти) пользователь получал
    «Переписка не найдена» вместо продолжения работы.
    """
    data = await state.get_data()
    chat_id = int(data.get("chat_id", -1) or -1)
    if chat_id >= 0:
        return chat_id

    # Запасной вариант: ID зашит в саму кнопку
    if isinstance(target, CallbackQuery):
        chat_id = C.chat_id_of(target.data or "")
        if chat_id >= 0:
            return chat_id

    # Последняя незавершённая переписка пользователя
    draft = await chats.get_draft(target.from_user.id)
    if draft is not None:
        return int(draft.id)
    return -1


async def _require_chat(target, state: FSMContext):
    """Загрузить конфиг текущей переписки.

    ``chat_id`` берётся из трёх источников по очереди:
      1) callback_data кнопки — она самодостаточна и всегда точна;
      2) состояние FSM — хранится в памяти и пустеет после перезапуска;
      3) последний черновик пользователя из БД.

    Раньше источником был исключительно ``state.get_data()``, поэтому после
    перезапуска бота (например, при обновлении версии) ввод текста,
    времени и фото отвечал «Переписка не найдена».
    """
    from bot.utils.errors import ChatNotFoundError

    event = _event_of(target)
    chats = get_services()["chats"]
    chat_id = await _resolve_chat_id(target, state, chats)
    if chat_id < 0:
        raise ChatNotFoundError()

    try:
        config = await chats.get_config(event.from_user.id, chat_id)
    except ChatNotFoundError:
        # Переписки могло не быть (удалена/сброшена) — берём черновик
        draft = await chats.get_draft(event.from_user.id)
        if draft is None:
            raise
        chat_id = int(draft.id)
        config = await chats.get_config(event.from_user.id, chat_id)

    # Синхронизируем FSM: отсюда берутся message_index, kind, side и т.п.
    data = await state.get_data()
    if data.get("chat_id") != chat_id:
        await state.update_data(chat_id=chat_id)
    return chat_id, config, event.from_user.id


def chats_author(config, message) -> str:
    if 0 <= message.author_index < len(config.participants):
        return config.participants[message.author_index].name
    return "Участник"


async def _save_and_back(
    target, state, config, chat_id, user_id, page: int = 0, header: str = ""
) -> None:
    """Сохранить конфиг и вернуться к списку сообщений."""
    await get_services()["chats"].save(user_id, chat_id, config)
    await state.set_state(Flow.editor)
    # Снимаем ввод: поле/индекс больше не должны влиять на след. действие.
    await state.update_data(chat_id=chat_id, field="", pending_text="", reply_to=None)
    await show_editor(target, config, chat_id, state, page, header=header)


def _apply_kind(message: Msg, kind: str) -> None:
    """Применить тип сообщения, создавая mock-медиа при необходимости."""
    from bot.schemas import MediaItem

    try:
        message.kind = MessageKind(kind)
    except ValueError:
        message.kind = MessageKind.TEXT
        return
    if message.kind == MessageKind.VOICE:
        message.media = MediaItem(kind=MessageKind.VOICE, duration=VOICE_DURATIONS[1])
    elif message.kind == MessageKind.FILE:
        message.media = MediaItem(
            kind=MessageKind.FILE,
            file_name=FILE_NAMES[0],
            file_size=FILE_SIZES[1],
        )
    elif message.kind == MessageKind.STICKER:
        message.media = MediaItem(kind=MessageKind.STICKER, emoji=STICKER_EMOJI[0])
    elif message.kind == MessageKind.IMAGE:
        _random_photo(message)
    else:
        message.media = None


def _random_photo(message: Msg) -> None:
    """Случайное фото-заглушка (без загрузки файла)."""
    import random

    from bot.schemas import MediaItem

    captions = ["", "Вот так", "Смотри", "Кадр из поездки", "Найдёшь?", "Скинул"]
    message.kind = MessageKind.IMAGE
    message.media = MediaItem(
        kind=MessageKind.IMAGE,
        caption=random.choice(captions),
        gradient=random.randint(0, 9),
    )


async def _start_add(
    callback: CallbackQuery, state: FSMContext, config, chat_id: int,
    user_id: int, side: int = -1, kind: str = "text", reply_to: Optional[str] = None,
) -> None:
    """Начать добавление нового сообщения.

    Перед началом ПОЛНОСТЬЮ перезаписываем состояние: старые ключи
    ``field``, ``message_index`` и ``pending_text`` оставались от
    предыдущей операции и ломали определение режима (правка vs добавление).
    """
    data = {"chat_id": chat_id, "kind": kind, "reply_to": reply_to}

    if side < 0:
        # Сначала спрашиваем отправителя
        await state.set_state(Flow.add_author)
        await state.update_data(**data, message_index=-1, field="author")
        await screens.ask(
            callback,
"👤 <b>Кто отправляет?</b>\n\nВыберите участника:",
            reply_markup=EK.author_menu(chat_id, T.author_labels(config), "new", -1),
        )
        return

    await state.set_state(Flow.add_text)
    await state.update_data(
        **data, side=side, message_index=-1, field="", pending_text=""
    )
    prompt = T.field_prompt("text")
    if kind == "service":
        prompt = T.field_prompt("service")
    elif kind == "date":
        prompt = T.field_prompt("date")
    elif kind == "forward":
        prompt = T.field_prompt("forward")
    await screens.ask(
            callback,
f"{prompt}\n\n{T.INPUT_CANCEL_HINT}",
            reply_markup=KB.input_menu("Введите текст…"),
        )


#: Действия, у которых есть ОТДЕЛЬНЫЙ хендлер ниже по файлу.
#: Если не исключить их из ``on_editor``, этот catch-all-хендлер
#: (он зарегистрирован ПЕРВЫМ, а aiogram берёт первое подходящее)
#: перехватит их все, и они будут отвечать «Сообщение не найдено».
SPECIFIC_ACTIONS = frozenset({
    "pickauthor", "settime", "manualtime", "preview", "done",
    "open_done", "save", "drop", "setdisc", "setopt", "setstyle", "clear",
})


class NotSpecificAction(BaseFilter):
    """Пропускает только те действия, у которых нет своего хендлера."""

    async def __call__(self, callback: CallbackQuery) -> bool:  # noqa: D102
        action = C.action(callback.data or "")
        return action not in SPECIFIC_ACTIONS


@router.callback_query(F.data.startswith(C.S_EDIT + ":"), NotSpecificAction())
async def on_editor(callback: CallbackQuery, state: FSMContext) -> None:
    """Навигация по списку сообщений и открытие экранов редактора."""
    action = C.action(callback.data)

    if action == "noop":
        await screens.safe_answer(callback)
        return
    if action in ("resume", "restart"):
        return  # обрабатывается в create.py
    if action == "home":
        await state.clear()
        await screens.show(callback, T.WELCOME, reply_markup=KB.main_menu())
        return

    if action == "page":
        chat_id, config, _ = await _require_chat(callback, state)
        await screens.safe_answer(callback)
        await show_editor(callback, config, chat_id, state, C.arg_int(callback.data, 0, 0))
        return

    # «Назад» из вложенных экранов редактора → список сообщений.
    # Раньше обработчик ``back`` открывал экран УЧАСТНИКОВ, поэтому
    # возврат из меню времени/реакции/медиа уводил в сторону.
    if action == "list":
        chat_id, config, _ = await _require_chat(callback, state)
        await state.set_state(Flow.editor)
        await show_editor(callback, config, chat_id, state)
        return

    if action == "participants":
        chat_id, config, _ = await _require_chat(callback, state)
        await state.set_state(Flow.participants)
        await state.update_data(chat_id=chat_id)
        await screens.show(
            callback, T.participants_screen(config), CK.participants_menu(config, chat_id)
        )
        return

    if action == "back":
        # Совместимость со старыми кнопками: «Назад» → редактор.
        chat_id, config, _ = await _require_chat(callback, state)
        await state.set_state(Flow.editor)
        await show_editor(callback, config, chat_id, state)
        return

    if action == "settings":
        chat_id, config, _ = await _require_chat(callback, state)
        from bot.keyboards.menus import chat_settings_menu

        await state.set_state(Flow.chat_settings)
        await state.update_data(chat_id=chat_id)
        await screens.show(
            callback, T.chat_summary(config), chat_settings_menu(chat_id)
        )
        return

    # --- Работа с сообщениями ---
    chat_id, config, user_id = await _require_chat(callback, state)
    data = await state.get_data()
    page = int(data.get("page", 0))

    if action == "open":
        index = C.index_of(callback.data, -1)
        if not (0 <= index < len(config.messages)):
            await screens.safe_answer(callback, "Сообщение не найдено.", alert=True)
            return
        message = config.messages[index]
        await state.set_state(Flow.message_menu)
        await state.update_data(chat_id=chat_id, message_index=index)
        await screens.show(
            callback,
            T.message_card(index + 1, message, chats_author(config, message)),
            EK.message_actions_menu(index, chat_id, config),
        )
        return

    if action == "add":
        side = C.arg_int(callback.data, 0, 0)
        await _start_add(callback, state, config, chat_id, user_id, side=side)
        return

    if action == "addmenu":
        await state.set_state(Flow.add_type)
        await state.update_data(chat_id=chat_id)
        await screens.show(
            callback,
            "➕ <b>Что добавить?</b>\n\nВыберите тип сообщения:",
            EK.add_message_menu(chat_id),
        )
        return

    if action == "new":
        await _start_add(
            callback, state, config, chat_id, user_id, kind=C.arg(callback.data, 0)
        )
        return

    # Единый разбор индекса: он всегда предпоследний аргумент
    # (см. C.index_of). Раньше здесь стоял фиксированный ``arg_int(data, 1)``,
    # из-за чего у кнопок ``ed:setreact:<emoji>:<chat_id>:<index>`` и
    # ``ed:settype:<key>:<chat_id>:<index>`` в «индекс» попадал chat_id.
    index = C.index_of(callback.data, -1)
    if not (0 <= index < len(config.messages)):
        await screens.safe_answer(callback, "Сообщение не найдено.", alert=True)
        return
    message = config.messages[index]

    if action == "edit":
        await state.set_state(Flow.add_text)
        await state.update_data(chat_id=chat_id, message_index=index, field="text")
        await screens.ask(
            callback,
f"✏️ <b>Сообщение {index + 1}</b>\n\n"
            f"Текущий текст: <code>{TX.esc(message.preview(200) or '—')}</code>\n\n"
            f"{T.field_prompt('text')}\n\n{T.INPUT_CANCEL_HINT}",
            reply_markup=KB.input_menu("Введите новый текст…"),
        )
        return

    if action == "time":
        await state.set_state(Flow.add_time)
        await state.update_data(chat_id=chat_id, message_index=index, field="time")
        await screens.ask(
            callback,
"🕐 <b>Время сообщения?</b>\n\n"
            "Текущее или вручную в формате <code>12:41</code>.",
            reply_markup=EK.time_menu(chat_id, index),
        )
        return

    if action in ("up", "down"):
        delta = -1 if action == "up" else 1
        new_index = config.move(index, delta)
        header = "↕️ Порядок изменён." if new_index != index else "↕️ Это край списка."
        await _save_and_back(callback, state, config, chat_id, user_id, new_index, header)
        return

    if action == "del":
        ChatService.delete_message(config, message.id)
        await _save_and_back(
            callback, state, config, chat_id, user_id, page, "🗑 Сообщение удалено."
        )
        return

    if action == "author":
        await state.set_state(Flow.add_author)
        await state.update_data(chat_id=chat_id, message_index=index, field="author")
        await screens.ask(
            callback,
"👤 <b>Кто отправляет это сообщение?</b>",
            reply_markup=EK.author_menu(chat_id, T.author_labels(config), "change", index),
        )
        return

    if action == "react":
        await screens.show(
            callback, "🙂 <b>Выберите реакцию</b>", EK.reaction_menu(index, chat_id)
        )
        return

    if action == "setreact":
        emoji = C.arg(callback.data, 0)
        if emoji == "-":
            message.reaction = None
        else:
            from bot.schemas import Reaction

            message.reaction = Reaction(emoji=emoji, count=1)
        await _save_and_back(callback, state, config, chat_id, user_id, index)
        return

    if action == "type":
        await screens.show(
            callback, "🧩 <b>Тип сообщения</b>", EK.type_menu(index, chat_id)
        )
        return

    if action == "settype":
        _apply_kind(message, C.arg(callback.data, 0))
        await _save_and_back(callback, state, config, chat_id, user_id, index)
        return

    if action == "media":
        await screens.show(
            callback, "🖼 <b>Медиа сообщения</b>", EK.media_menu(index, chat_id)
        )
        return

    if action == "nomedia":
        message.media = None
        if message.kind not in (MessageKind.TEXT, MessageKind.SERVICE):
            message.kind = MessageKind.TEXT
        await _save_and_back(callback, state, config, chat_id, user_id, index)
        return

    if action == "randphoto":
        _random_photo(message)
        await _save_and_back(callback, state, config, chat_id, user_id, index)
        return

    if action == "photo":
        await state.set_state(Flow.media)
        await state.update_data(chat_id=chat_id, message_index=index)
        await screens.ask(
            callback,
"📷 <b>Пришлите фотографию</b>\n\nОна станет вложением к сообщению.",
            reply_markup=KB.input_menu("Отправьте фото…"),
        )
        return

    if action == "replytarget":
        target_index = C.index_of(callback.data, -1)
        if not (0 <= target_index < len(config.messages)):
            await screens.safe_answer(callback, "Сообщение не найдено.", alert=True)
            return
        await _start_add(
            callback, state, config, chat_id, user_id,
            reply_to=config.messages[target_index].id,
        )
        return

    await screens.safe_answer(callback, "Неизвестное действие.", alert=True)


@router.callback_query(F.data.startswith(C.S_EDIT + ":pickauthor"))
async def on_pick_author(callback: CallbackQuery, state: FSMContext) -> None:
    """Выбор отправителя (для нового сообщения или смены автора).

    Формат кнопки: ``ed:pickauthor:<i>:<action>:<index>:<chat_id>``.
    """
    chat_id = C.chat_id_of(callback.data)
    index = C.index_of(callback.data, -1)
    action = C.arg(callback.data, 1)      # "new" | "change"
    side = 0 if C.arg_int(callback.data, 0, 0) == 0 else 1

    if chat_id < 0:
        chat_id, _config, _uid = await _resolve_chat(callback, state)
    config = await get_services()["chats"].get_config(callback.from_user.id, chat_id)

    data = await state.get_data()
    kind = str(data.get("kind", "text"))
    reply_to = data.get("reply_to")

    if action == "change" and 0 <= index < len(config.messages):
        message = config.messages[index]
        message.side = side
        message.author_index = side
        await _save_and_back(
            callback, state, config, chat_id, callback.from_user.id, index,
            "👤 Автор изменён.",
        )
        return

    await state.set_state(Flow.add_text)
    await state.update_data(chat_id=chat_id, side=side, kind=kind, reply_to=reply_to)
    prompt = {
        "service": T.field_prompt("service"),
        "date": T.field_prompt("date"),
        "forward": T.field_prompt("forward"),
    }.get(kind, T.field_prompt("text"))
    await screens.ask(
            callback,
f"{prompt}\n\n{T.INPUT_CANCEL_HINT}",
            reply_markup=KB.input_menu("Введите текст…"),
        )


async def _resolve_chat(callback: CallbackQuery, state: FSMContext):
    """Загрузить переписку по кнопке, при неудаче — из FSM."""
    chat_id, config, user_id = await _require_chat(callback, state)
    return chat_id, config, user_id


@router.callback_query(F.data.startswith(C.S_EDIT + ":settime"))
async def on_set_time(callback: CallbackQuery, state: FSMContext) -> None:
    """Установка текущего времени.

    Формат кнопки: ``ed:settime:now:<index>:<chat_id>`` — ``chat_id``
    последний, ``index`` предпоследний.

    Раньше разбор шёл так: ``chat_id_of`` возвращал последний аргумент,
    а последним был ``index``. В итоге вместо ``chat_id`` в запрос попадал
    индекс сообщения, и пользователь видел «Переписка не найдена» ровно
    при установке времени. Плюс ``_ask_time`` передавал в меню
    ``chat_id = -1``, что ломало и так.
    """
    chat_id = C.chat_id_of(callback.data)
    index = C.index_of(callback.data, -1)

    if chat_id < 0:
        chat_id, _config, _uid = await _resolve_chat(callback, state)

    chats = get_services()["chats"]
    config = await chats.get_config(callback.from_user.id, chat_id)
    now = current_time_str()

    if action_is_new(index):
        # Новое сообщение: фиксируем время и только теперь создаём его.
        await _commit_message(
            callback, state, config, chat_id, callback.from_user.id, time_value=now
        )
        return

    if 0 <= index < len(config.messages):
        config.messages[index].time = now
        await _save_and_back(
            callback, state, config, chat_id, callback.from_user.id, index,
            f"🕐 Время: {now}",
        )
        return

    await screens.safe_answer(callback, "Сообщение не найдено.", alert=True)


def action_is_new(index: int) -> bool:
    """index == -1 означает «новое сообщение»."""
    return index < 0


@router.callback_query(F.data.startswith(C.S_EDIT + ":manualtime"))
async def on_manual_time(callback: CallbackQuery, state: FSMContext) -> None:
    """Ручной ввод времени. Формат: ``ed:manualtime:<index>:<chat_id>``."""
    chat_id = C.chat_id_of(callback.data)
    index = C.index_of(callback.data, -1)

    if chat_id < 0:
        chat_id, _config, _uid = await _resolve_chat(callback, state)

    await state.set_state(Flow.manual_time)
    await state.update_data(chat_id=chat_id, message_index=index, field="time")
    await screens.ask(
            callback,
"⌨️ <b>Введите время</b>\n\nФормат: <code>12:41</code>, <code>23:07</code>, "
            "<code>09:15</code>",
            reply_markup=KB.input_menu("Например: 12:41"),
        )


@router.message(Flow.manual_time, F.text)
async def on_manual_time_input(message: Message, state: FSMContext) -> None:
    """Обработка введённого времени."""
    data = await state.get_data()
    chat_id = await _state_chat_id(data, message.from_user.id)
    index = int(data.get("message_index", -1))
    raw = (message.text or "").strip()

    try:
        value = parse_time(raw)
    except InvalidTimeError:
        await message.answer(
            "Неверное время. Формат: <code>12:41</code> (часы 0–23, минуты 0–59).",
            parse_mode=screens.PARSE_MODE,
        )
        return

    chats = get_services()["chats"]
    config = await chats.get_config(message.from_user.id, chat_id)
    if index < 0:
        await _commit_message(message, state, config, chat_id, message.from_user.id,
                              time_value=value)
        return
    if 0 <= index < len(config.messages):
        config.messages[index].time = value
        await _save_and_back(
            message, state, config, chat_id, message.from_user.id, index, f"🕐 Время: {value}"
        )
        return
    await message.answer("Сообщение больше не существует. Откройте редактор заново.")
    await state.set_state(Flow.editor)
    await state.update_data(chat_id=chat_id, page=0, field="", pending_text="")
    await show_editor(message, config, chat_id, state, 0)


async def _commit_message(
    target, state, config, chat_id: int, user_id: int,
    time_value: Optional[str] = None,
) -> None:
    """Добавить новое сообщение в переписку (с проверкой лимита)."""
    data = await state.get_data()
    side = 0 if int(data.get("side", 0)) == 0 else 1
    kind = str(data.get("kind", "text"))
    reply_to = data.get("reply_to")
    text = str(data.get("pending_text", ""))
    forward_from = str(data.get("forward_from", ""))

    message = Msg(
        kind=_safe_kind(kind),
        text=text,
        time=time_value or current_time_str(),
        side=side,
        author_index=side,
        reply_to=reply_to,
        forward_from=forward_from,
        read=side == 0 or int(data.get("seq", 0)) % 3 != 0,
    )
    _apply_kind(message, kind)
    if message.kind == MessageKind.SERVICE or message.kind == MessageKind.DATE:
        message.side = 0
        message.author_index = 0

    # Сервисы берём из .data того же объекта (Message или CallbackQuery).
    # Раньше здесь стояло hasattr(target, "data"): для Message это всегда
    # False (у Message нет поля data), а для CallbackQuery — всегда True
    # (поле есть, но это строка), поэтому ветка выбиралась неверно.
    limits = get_services()["limits"]
    max_messages = limits.max_messages(is_premium())

    if len(config.messages) >= max_messages:
        page = max(0, (len(config.messages) - 1) // PER_PAGE)
        await state.set_state(Flow.editor)
        await state.update_data(
            chat_id=chat_id,
            page=page,
            field="",
            pending_text="",
            forward_from="",
            reply_to=None,
        )
        await show_editor(
            target,
            config,
            chat_id,
            state,
            page,
            header=(
                f"⚠️ Достигнут лимит: максимум {max_messages} сообщений. "
                "Удалите лишнее или сохраните переписку."
            ),
        )
        return

    config.settings.max_messages = max_messages
    config.messages.append(message)
    index = len(config.messages) - 1
    # Чистим временные ключи: иначе следующая правка сообщения будет
    # ошибочно принята за продолжение добавления нового.
    await state.update_data(
        message_index=index,
        field="",
        pending_text="",
        forward_from="",
        reply_to=None,
    )
    await _save_and_back(
        target, state, config, chat_id, user_id, index,
        "✅ Сообщение добавлено.",
    )


def _safe_kind(kind: str) -> MessageKind:
    try:
        return MessageKind(kind)
    except ValueError:
        return MessageKind.TEXT


@router.message(Flow.add_text, F.text)
async def on_add_text(message: Message, state: FSMContext) -> None:
    """Ввод текста нового сообщения или правка существующего."""
    data = await state.get_data()
    chat_id = await _state_chat_id(data, message.from_user.id)
    index = int(data.get("message_index", -1))
    text = TX.clean_multiline(message.text or "")

    if not text:
        await message.answer("Текст не может быть пустым. Попробуйте ещё раз.")
        return
    if len(text) > TX.MAX_MESSAGE_LENGTH:
        await message.answer(
            f"Текст слишком длинный ({len(text)} символов). "
            f"Максимум {TX.MAX_MESSAGE_LENGTH}."
        )
        return

    chats = get_services()["chats"]
    config = await chats.get_config(message.from_user.id, chat_id)
    kind = str(data.get("kind", "text"))

    # Режим правки определяется полем ``field == "text"``, а не наличием
    # ключа ``side`` в состоянии. Раньше проверка была ``"side" not in data``:
    # после добавления первого сообщения в состоянии навсегда оставался
    # ``side``, и последующая правка существующего сообщения молча
    # превращалась в добавление НОВОГО сообщения — «правка не сохранялась».
    if str(data.get("field", "")) == "text" and index >= 0:
        if 0 <= index < len(config.messages):
            config.messages[index].text = TX.clamp_multiline(
                text, TX.MAX_MESSAGE_LENGTH
            )
            config.messages[index].edited = True
            await _save_and_back(
                message, state, config, chat_id, message.from_user.id, index,
                "✏️ Сообщение изменено.",
            )
            return
        await message.answer(
            "Сообщение больше не существует. Откройте переписку заново.",
            reply_markup=KB.main_menu(),
        )
        await state.clear()
        return

    if kind == "forward":
        await state.update_data(pending_text=text, message_index=-1)
        await state.set_state(Flow.add_time)
        await message.answer(
            f"↪ От кого переслано? (введите имя)\n\n{T.INPUT_CANCEL_HINT}",
            parse_mode=screens.PARSE_MODE,
            reply_markup=KB.input_menu("Имя отправителя"),
        )
        return

    await state.update_data(pending_text=text, message_index=-1)
    await _ask_time(message, state, chat_id)


async def _ask_time(target, state: FSMContext, chat_id: int = -1) -> None:
    """Спросить время сообщения.

    ``chat_id`` ОБЯЗАТЕЛЬНО передаётся дальше в меню времени. Раньше здесь
    стояло ``EK.time_menu(-1, -1)`` — кнопка несла ``chat_id = -1``, и
    нажатие «Текущее время» всегда давало «Переписка не найдена».
    """
    if chat_id < 0:
        chat_id = int((await state.get_data()).get("chat_id", -1))
    await state.set_state(Flow.add_time)
    await target.answer(
        "🕐 <b>Время сообщения?</b>\n\n"
        "Выберите текущее время или укажите вручную (<code>12:41</code>).",
        parse_mode=screens.PARSE_MODE,
        reply_markup=EK.time_menu(chat_id, -1),
    )


@router.message(Flow.media, F.photo)
async def on_media_photo(message: Message, state: FSMContext, bot: Bot) -> None:
    """Замена медиа на фотографию, отправленную из Telegram."""
    from bot.handlers.create import _download_photo
    from bot.schemas import MediaItem

    data = await state.get_data()
    chat_id = await _state_chat_id(data, message.from_user.id)
    index = int(data.get("message_index", -1))
    chats = get_services()["chats"]
    config = await chats.get_config(message.from_user.id, chat_id)

    if not (0 <= index < len(config.messages)):
        await message.answer("Сообщение больше не существует. Откройте редактор заново.")
        await state.set_state(Flow.editor)
        await state.update_data(chat_id=chat_id, page=0, field="")
        await show_editor(message, config, chat_id, state, 0)
        return
    path = await _download_photo(bot, message.photo[-1].file_id, message.from_user.id)
    if path is None:
        await message.answer("Не удалось загрузить фото. Попробуйте другое изображение.")
        return
    target = config.messages[index]
    target.kind = MessageKind.IMAGE
    target.media = MediaItem(kind=MessageKind.IMAGE, path=str(path))
    await _save_and_back(
        message, state, config, chat_id, message.from_user.id, index, "🖼 Фото добавлено."
    )


@router.message(Flow.add_time, F.text)
async def on_time_text(message: Message, state: FSMContext) -> None:
    """Ввод имени источника пересылки или времени в состоянии add_time."""
    data = await state.get_data()
    chat_id = await _state_chat_id(data, message.from_user.id)
    text = (message.text or "").strip()
    kind = str(data.get("kind", "text"))

    chats = get_services()["chats"]
    config = await chats.get_config(message.from_user.id, chat_id)

    if kind == "forward":
        if not text:
            await message.answer("Укажите, от кого переслано сообщение.")
            return
        await state.update_data(forward_from=TX.clamp(text, 48))
        await _commit_message(
            message,
            state,
            config,
            chat_id,
            message.from_user.id,
            current_time_str(),
        )
        return

    try:
        value = parse_time(text)
    except InvalidTimeError:
        await message.answer(
            "Неверный ввод. Формат времени: <code>12:41</code>.",
            parse_mode=screens.PARSE_MODE,
            # chat_id обязателен: с -1 кнопка «Текущее время» снова
            # привела бы к «Переписка не найдена».
            reply_markup=EK.time_menu(chat_id, -1),
        )
        return
    await _commit_message(message, state, config, chat_id, message.from_user.id, value)


# --- Предпросмотр и завершение ----------------------------------------
async def _send_render(
    target, state, config, chat_id: int, user_id: int,
    caption: str, keyboard, header: str = "",
) -> bool:
    """Сгенерировать изображение с учётом лимитов и отправить его."""
    services = get_services()
    limits = services["limits"]
    users = services["user"]
    chats = services["chats"]
    premium = is_premium()

    check = await limits.reserve_image(user_id, premium)
    if not check:
        await screens.notify(target, check.text or "Лимит генераций исчерпан.")
        return False

    status = await _status_message(target, "⏳ Генерирую изображение…")
    if isinstance(target, CallbackQuery):
        await screens.safe_answer(target)
    try:
        photo = await render_service.render_bytes(config)
    except Exception:  # noqa: BLE001
        logger.exception("Ошибка генерации изображения")
        await _edit_status(
            target, status, "❌ Не удалось сгенерировать изображение. Попробуйте ещё раз."
        )
        return False

    # Передаём Message (или сам CallbackQuery), а не .chat: у Chat нет
    # метода send_photo — было AttributeError: 'Chat' object has no
    # attribute 'send_photo'.
    sent = await screens.send_photo(target, photo, caption, keyboard)
    await _edit_status(target, status, "")
    if sent is None:
        return False
    await limits.log_image(user_id, str(chat_id))
    await users.count_image(user_id)
    await chats.count_render(chat_id)
    return True


async def _status_message(target, text: str):
    event = target if isinstance(target, Message) else target.message
    try:
        return await event.answer(text, parse_mode=screens.PARSE_MODE)
    except Exception:  # noqa: BLE001
        return None


async def _edit_status(target, status, text: str) -> None:
    if status is None:
        return
    try:
        if text:
            await status.edit_text(text, parse_mode=screens.PARSE_MODE)
        else:
            await status.delete()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Не удалось обновить статус: %s", exc)


@router.callback_query(F.data.startswith(C.S_EDIT + ":preview"))
async def on_preview(callback: CallbackQuery, state: FSMContext) -> None:
    """Предпросмотр: сгенерировать и отправить изображение."""
    chat_id, config, user_id = await _require_chat(callback, state)
    try:
        ChatService.require_content(config)
    except NoMessagesError as exc:
        await screens.safe_answer(callback, exc.user_message, alert=True)
        return

    await get_services()["chats"].save(user_id, chat_id, config)
    ok = await _send_render(
        callback, state, config, chat_id, user_id,
        "👀 <b>Предпросмотр</b>\n\nЭто фиктивная переписка для юмора и контента.",
        EK.preview_keyboard(chat_id),
    )
    if ok:
        await state.set_state(Flow.editor)
    else:
        await screens.safe_answer(callback)


@router.callback_query(F.data.startswith(C.S_EDIT + ":done"))
async def on_done(callback: CallbackQuery, state: FSMContext) -> None:
    """Готовое изображение переписки."""
    chat_id, config, user_id = await _require_chat(callback, state)
    try:
        ChatService.require_content(config)
    except NoMessagesError as exc:
        await screens.safe_answer(callback, exc.user_message, alert=True)
        return

    await get_services()["chats"].save(user_id, chat_id, config)
    # Текст подписи зависит от того, включена ли пометка
    if (config.disclaimer or "").strip():
        note = "На изображении есть пометка «FICTIONAL CHAT»."
    else:
        note = (
            "Пометка на изображении выключена — включить её можно "
            "в настройках переписки."
        )
    ok = await _send_render(
        callback, state, config, chat_id, user_id,
        "✅ <b>Готово.</b>\n\n"
        "Это фиктивная переписка, созданная в конструкторе.\n\n"
        f"{note}",
        EK.done_keyboard(chat_id),
    )
    if ok:
        await state.update_data(finished=True)
    else:
        await screens.safe_answer(callback)


@router.callback_query(F.data.startswith(C.S_EDIT + ":open_done"))
async def on_open_done(callback: CallbackQuery, state: FSMContext) -> None:
    """Вернуться в редактор из готового изображения."""
    chat_id, config, user_id = await _require_chat(callback, state)
    await state.set_state(Flow.editor)
    await state.update_data(finished=False)
    await show_editor(
        callback, config, chat_id, state, 0, header="🔄 <b>Редактирование</b>"
    )


@router.callback_query(F.data.startswith(C.S_EDIT + ":save"))
async def on_save(callback: CallbackQuery, state: FSMContext) -> None:
    """Сохранить переписку в «Мои переписки»."""
    chat_id, config, user_id = await _require_chat(callback, state)
    try:
        ChatService.require_content(config)
    except NoMessagesError as exc:
        await screens.safe_answer(callback, exc.user_message, alert=True)
        return
    chats = get_services()["chats"]
    chat = await chats.finish(user_id, chat_id, config)
    await screens.show(
        callback,
        f"📂 <b>Сохранено</b>\n\n"
        f"Переписка #{chat.id} добавлена в «Мои переписки».\n"
        f"{TX.messages_word(len(config.messages))}",
        EK.done_keyboard(chat_id),
    )


@router.callback_query(F.data.startswith(C.S_EDIT + ":drop"))
async def on_drop(callback: CallbackQuery, state: FSMContext) -> None:
    """Удалить переписку."""
    chat_id = C.chat_id_of(callback.data)
    chats = get_services()["chats"]
    if chat_id < 0:
        await screens.safe_answer(callback, "Переписка не найдена.", alert=True)
        return
    try:
        await chats.delete(callback.from_user.id, chat_id)
    except ChatNotFoundError as exc:
        await screens.safe_answer(callback, exc.user_message, alert=True)
        return
    await state.clear()
    await screens.show(
        callback, "🗑 Переписка удалена.\n\n" + T.WELCOME, reply_markup=KB.main_menu()
    )


# --- Настройки переписки ------------------------------------------------
SETTING_MAP = {
    "time": "show_time",
    "checks": "show_checks",
    "read": "show_read",
    "reactions": "show_reactions",
    "avatars": "show_avatars_in_header",
    "tail": "show_tail",
    "pattern": "show_pattern",
    "dividers": "date_dividers",
}

@router.callback_query(F.data.startswith(C.S_EDIT + ":setdisc"))
async def on_set_disclaimer(callback: CallbackQuery, state: FSMContext) -> None:
    """Включение/выключение и смена текста пометки."""
    from bot.keyboards.menus import disclaimer_picker

    chat_id, config, user_id = await _require_chat(callback, state)
    # Ключ приходит коротким (NONE/EN/RU/BOTH) — так callback_data
    # укладывается в лимит Telegram в 64 байта.
    key = C.arg(callback.data, 0)
    config.disclaimer = C.disclaimer_of(key)
    await get_services()["chats"].save(user_id, chat_id, config)
    # Раньше экран НЕ обновлялся: пометка менялась, но пользователь видел
    # старый список и нажимал «Назад», полагая, что ничего не сохранилось.
    await screens.show(
        callback,
        "⚠️ <b>Пометка на изображении</b>\n\n"
        + (f"Сейчас на изображении: <b>{TX.esc(config.disclaimer)}</b>"
           if config.disclaimer else "Пометка выключена."),
        disclaimer_picker(chat_id, config.disclaimer),
    )


@router.callback_query(F.data.startswith(C.S_EDIT + ":setopt"))
async def on_set_option(callback: CallbackQuery, state: FSMContext) -> None:
    """Переключение настроек отображения переписки."""
    from bot.keyboards.menus import chat_settings_menu, disclaimer_picker, style_picker

    option = C.arg(callback.data, 0)
    chat_id, config, user_id = await _require_chat(callback, state)

    if option == "style":
        premium = bool(is_premium())
        await screens.show(
            callback, "🎨 <b>Стиль интерфейса</b>", style_picker(chat_id, config.style, premium)
        )
        return

    if option == "disclaimer":
        await screens.show(
            callback,
            "⚠️ <b>Пометка на изображении</b>",
            disclaimer_picker(chat_id, config.disclaimer),
        )
        return

    field = SETTING_MAP.get(option)
    if field is None:
        await screens.safe_answer(callback, "Неизвестная настройка.", alert=True)
        return
    setattr(config.settings, field, not getattr(config.settings, field))
    await get_services()["chats"].save(user_id, chat_id, config)
    await screens.show(callback, T.chat_summary(config), chat_settings_menu(chat_id))


@router.callback_query(F.data.startswith(C.S_EDIT + ":setstyle"))
async def on_set_style(callback: CallbackQuery, state: FSMContext) -> None:
    """Смена стиля интерфейса переписки."""
    from bot.generators import AVAILABLE_STYLES
    from bot.keyboards.menus import chat_settings_menu

    chat_id, config, user_id = await _require_chat(callback, state)
    style = C.arg(callback.data, 0)
    definition = next((s for s in AVAILABLE_STYLES if s.key == style), None)
    if definition is None:
        await screens.safe_answer(callback, "Неизвестный стиль.", alert=True)
        return
    premium = bool(is_premium())
    if definition.premium_only and not premium:
        await screens.safe_answer(callback, "Стиль доступен в Premium.", alert=True)
        return
    config.style = style
    await get_services()["chats"].save(user_id, chat_id, config)
    await screens.show(
        callback,
        f"🎨 Стиль изменён на <b>{definition.title}</b>.",
        chat_settings_menu(chat_id),
    )


@router.callback_query(F.data.startswith(C.S_EDIT + ":clear"))
async def on_clear_messages(callback: CallbackQuery, state: FSMContext) -> None:
    """Очистить все сообщения переписки."""
    chat_id, config, user_id = await _require_chat(callback, state)
    config.messages.clear()
    await get_services()["chats"].save(user_id, chat_id, config)
    await state.set_state(Flow.editor)
    await show_editor(callback, config, chat_id, state, 0, header="🗑 Сообщения очищены.")


__all__ = [
    "router", "show_editor", "on_editor", "on_pick_author", "on_set_time",
    "on_manual_time", "on_add_text", "on_time_text", "on_media_photo",
    "on_preview", "on_done", "on_save", "on_drop", "on_set_option",
    "on_set_style", "on_set_disclaimer", "on_clear_messages", "pages_of",
]