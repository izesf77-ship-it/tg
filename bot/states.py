"""FSM-состояния бота (aiogram 3)."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Flow(StatesGroup):
    """Все состояния редактора переписки."""

    # --- Создание ---
    style = State()               # выбор стиля интерфейса
    participants = State()        # список участников
    participant = State()         # карточка участника
    participant_input = State()   # ввод поля участника

    # --- Редактор ---
    editor = State()              # список сообщений
    message_menu = State()        # действия с сообщением
    add_type = State()            # выбор типа нового сообщения
    add_author = State()          # выбор отправителя
    add_text = State()            # ввод текста сообщения
    add_time = State()            # выбор времени
    add_manual_time = State()     # ручной ввод времени
    media = State()               # приём фото
    forward_source = State()      # имя источника пересылки
    reply_target = State()        # выбор сообщения для ответа

    # --- Настройки ---
    chat_settings = State()
    manual_time = State()         # ввод времени для существующего сообщения
    disclaimer = State()

    # --- AI и админка ---
    ai_prompt = State()
    broadcast_text = State()
    admin_limit = State()


class Global(StatesGroup):
    """Состояния верхнего уровня."""

    idle = State()


#: Удобные имена для переходов
IDLE = None  # None означает «сбросить состояние»

__all__ = ["Flow", "Global", "IDLE"]
