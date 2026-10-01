"""Middleware: подключение сессии БД и сервисов к каждому апдейту."""

from __future__ import annotations

import logging
from contextvars import ContextVar, Token
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import (
    CallbackQuery,
    Message,
    PreCheckoutQuery,
    TelegramObject,
    User as TgUser,
)

from bot.database.engine import session_scope
from bot.services.chat_service import bind as bind_chats
from bot.services.limit_service import bind as bind_limits
from bot.services.user_service import bind as bind_user

logger = logging.getLogger(__name__)

CTX_KEY = "bot_context"


class _Context:
    """Данные сессии, доступные хендлерам."""

    __slots__ = ("session", "services", "db_user")

    def __init__(self, session, services, db_user) -> None:
        self.session = session
        self.services = services
        self.db_user = db_user


# Контекст хранится в ContextVar, а НЕ в объекте события.
# Причина: у aiogram Message нет поля data, а у CallbackQuery поле data
# занято строкой callback-данных — достать services из объекта невозможно.
_ctx_var: ContextVar[_Context] = ContextVar("bot_context", default=None)


def set_context(ctx: _Context) -> Token:
    """Записать контекст обработки текущего события."""
    return _ctx_var.set(ctx)


def reset_context(token: Token) -> None:
    _ctx_var.reset(token)


def get_context() -> _Context:
    """Текущий контекст обработки события."""
    ctx = _ctx_var.get()
    if ctx is None:
        raise RuntimeError(
            "Контекст не инициализирован: хендлер вызван без DbSessionMiddleware"
        )
    return ctx


def get_services() -> Dict[str, Any]:
    """Сервисы текущего события: chats, limits, user."""
    return get_context().services


def get_db_user():
    """Пользователь из БД."""
    return get_context().db_user


def db_session():
    """Активная сессия БД."""
    return get_context().session


def is_premium() -> bool:
    """Premium-статус текущего пользователя (безопасно)."""
    from bot.services.premium_service import premium_service

    return premium_service.is_premium(get_db_user())


class DbSessionMiddleware(BaseMiddleware):
    """Открывает сессию БД и кладёт сервисы в data на время обработки.

    ВАЖНО: доступ к данным идёт только через ``bot.middleware.get_context``,
    а не через ``event.data``. У aiogram у ``Message`` нет поля ``data``,
    а у ``CallbackQuery`` поле ``data`` — это строка callback-данных,
    поэтому обращение вида ``message.data["services"]`` всегда падало.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is None and isinstance(
            event, (Message, CallbackQuery, PreCheckoutQuery)
        ):
            tg_user = event.from_user

        # Бот и чат события: нужны, чтобы отправить изображение даже из
        # callback'а без сообщения (у него нет .message.bot/.message.chat).
        from bot import screens as _screens

        _event_bot = data.get("bot")
        _event_chat = getattr(event, "chat", None)
        if isinstance(event, CallbackQuery) and event.message is not None:
            _event_bot = _event_bot or event.message.bot
            _event_chat = _event_chat or event.message.chat
        _screens.bind_event_context(_event_bot, getattr(_event_chat, "id", None))

        if tg_user is None:
            return await handler(event, data)

        async with session_scope() as session:
            # bind() создаёт экземпляр сервиса, привязанный к сессии,
            # и возвращает его. Раньше здесь вызывался метод
            # user_service.bind(session) — но user_service это модуль,
            # а bind() — функция, поэтому было AttributeError.
            users_svc = bind_user(session)
            limits_svc = bind_limits(session)
            chats_svc = bind_chats(session)
            data["session"] = session
            # Ключи сервисов: "chats", "limits", "user" (без "users").
            services = {
                "user": users_svc,
                "limits": limits_svc,
                "chats": chats_svc,
            }
            data["services"] = services
            try:
                user = await users_svc.register(tg_user)
            except Exception as exc:  # noqa: BLE001 - БД не должна ронять бота
                logger.exception("Не удалось зарегистрировать пользователя")
                # Сессия после ошибки flush непригодна: без rollback
                # следующий commit даст PendingRollbackError
                try:
                    await session.rollback()
                except Exception:  # noqa: BLE001
                    pass
                user = None

            data["db_user"] = user
            if user is not None and user.is_banned:
                logger.info("Попытка входа заблокированного пользователя %s", user.id)
                await _notify_banned(event)
                return None

            if user is not None:
                # Антиспам: фиксируем действия пользователя
                if not _is_control_message(event):
                    async with limits_svc.rate_lock(user.id):
                        spam_check = await limits_svc.check_spam(user.id)
                        if not spam_check:
                            await _notify_rate_limited(event, spam_check.text)
                            return None
                        await limits_svc.log_action(user.id)
                        await session.commit()

            # Контекст в ContextVar: хендлеры читают сервисы без аргументов
            token = set_context(
                _Context(session=session, services=services, db_user=user)
            )
            try:
                return await handler(event, data)
            finally:
                reset_context(token)


async def _notify_banned(event: TelegramObject) -> None:
    text = "🚫 Ваш аккаунт заблокирован. Обратитесь к администратору."
    try:
        if isinstance(event, Message):
            await event.answer(text)
        elif isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
        elif isinstance(event, PreCheckoutQuery):
            await event.answer(ok=False, error_message=text[:200])
    except Exception as exc:  # noqa: BLE001 # pragma: no cover
        logger.debug("Не удалось отправить уведомление о блокировке: %s", exc)


def _is_control_message(event: TelegramObject) -> bool:
    if isinstance(event, PreCheckoutQuery):
        return True
    if not isinstance(event, Message):
        return False
    text = (event.text or "").strip()
    command = text.split(maxsplit=1)[0].split("@")[0].lower() if text else ""
    if command in ("/start", "/cancel"):
        return True
    from bot.keyboards.common import BTN_CANCEL

    return text == BTN_CANCEL


async def _notify_rate_limited(event: TelegramObject, text: str) -> None:
    message = text or "Слишком много действий. Подождите минуту."
    try:
        if isinstance(event, Message):
            await event.answer(message)
        elif isinstance(event, CallbackQuery):
            await event.answer(message, show_alert=True)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Не удалось показать ограничение частоты: %s", exc)


class ErrorMiddleware(BaseMiddleware):
    """Превращает исключения в понятный ответ пользователю."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        from bot.utils.errors import BotError

        try:
            return await handler(event, data)
        except BotError as exc:
            logger.info("Пользовательская ошибка: %s", exc.user_message)
            await _send_error(event, exc.user_message)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Непредвиденная ошибка при обработке события")
            await _send_error(
                event,
                "Внутренняя ошибка. Попробуйте ещё раз или используйте /start.",
            )
        return None


async def _send_error(event: TelegramObject, text: str) -> None:
    try:
        if isinstance(event, Message):
            await event.answer(text)
        elif isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
        elif isinstance(event, PreCheckoutQuery):
            await event.answer(ok=False, error_message=text[:200])
    except Exception as exc:  # noqa: BLE001 # pragma: no cover
        logger.debug("Не удалось отправить сообщение об ошибке: %s", exc)


__all__ = [
    "DbSessionMiddleware",
    "ErrorMiddleware",
    "get_context",
    "get_services",
    "get_db_user",
    "db_session",
    "is_premium",
    "set_context",
    "reset_context",
]
