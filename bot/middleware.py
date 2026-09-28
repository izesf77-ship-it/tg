"""Middleware: подключение сессии БД и сервисов к каждому апдейту."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User as TgUser

from bot.database.engine import session_scope
from bot.services import chat_service, limit_service, user_service

logger = logging.getLogger(__name__)

CTX_KEY = "bot_context"


class _Context:
    """Данные сессии, доступные хендлерам."""

    __slots__ = ("session", "services", "db_user")

    def __init__(self, session, services, db_user) -> None:
        self.session = session
        self.services = services
        self.db_user = db_user


def get_context(data: Dict[str, Any]) -> _Context:
    """Достать контекст из данных события.

    aiogram не кладёт ``data`` в объект Message, а поле ``data`` у
    CallbackQuery занято строкой callback-данных. Поэтому хендлеры должны
    получать сервисы отсюда, а не через ``event.data``.
    """
    ctx = data.get(CTX_KEY)
    if ctx is None:
        # Страховка на случай прямого вызова хендлера в тестах
        ctx = _Context(
            session=data.get("session"),
            services=data.get("services") or {},
            db_user=data.get("db_user"),
        )
    return ctx


def get_services(data: Dict[str, Any]) -> Dict[str, Any]:
    return get_context(data).services


def get_db_user(data: Dict[str, Any]):
    return get_context(data).db_user


def is_premium(data: Dict[str, Any]) -> bool:
    """Premium-статус текущего пользователя (безопасно)."""
    return bool(getattr(get_db_user(data), "is_premium", False))


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
        if tg_user is None and isinstance(event, (Message, CallbackQuery)):
            tg_user = event.from_user

        if tg_user is None:
            return await handler(event, data)

        async with session_scope() as session:
            user_service.bind(session)
            limit_service.bind(session)
            chat_service.bind(session)
            data["session"] = session
            # Ключи сервисов: "chats", "limits", "user" (без "users").
            data["services"] = {
                "user": user_service,
                "limits": limit_service,
                "chats": chat_service,
            }
            # Единая точка доступа для хендлеров
            data[CTX_KEY] = _Context(
                session=session,
                services=data["services"],
                db_user=None,
            )
            try:
                user = await user_service.register(tg_user)
            except Exception as exc:  # noqa: BLE001 - БД не должна ронять бота
                logger.exception("Не удалось зарегистрировать пользователя")
                return await handler(event, data)

            data["db_user"] = user
            data[CTX_KEY] = _Context(
                session=session, services=data["services"], db_user=user
            )
            if user.is_banned:
                logger.info("Попытка входа заблокированного пользователя %s", user.id)
                await _notify_banned(event)
                return None

            # Антиспам: фиксируем действия пользователя
            try:
                await limit_service.log_action(user.id)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Не удалось записать действие: %s", exc)

            return await handler(event, data)


async def _notify_banned(event: TelegramObject) -> None:
    text = "🚫 Ваш аккаунт заблокирован. Обратитесь к администратору."
    try:
        if isinstance(event, Message):
            await event.answer(text)
        elif isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
    except Exception as exc:  # noqa: BLE001 # pragma: no cover
        logger.debug("Не удалось отправить уведомление о блокировке: %s", exc)


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
    except Exception as exc:  # noqa: BLE001 # pragma: no cover
        logger.debug("Не удалось отправить сообщение об ошибке: %s", exc)


__all__ = [
    "DbSessionMiddleware",
    "ErrorMiddleware",
    "get_context",
    "get_services",
    "get_db_user",
    "is_premium",
]
