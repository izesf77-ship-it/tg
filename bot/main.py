"""Точка входа: сборка Dispatcher, роутеров и запуск polling."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import (
    RestartingTelegram,
    TelegramConflictError,
    TelegramNetworkError,
    TelegramServerError,
)
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.config import settings
from bot.database.engine import create_all, dispose_engine
from bot.database.repositories import UsageRepository
from bot.generators.fonts import get_font_manager
from bot.health import set_status, start_health_server
from bot.handlers import admin, ai, create, editor, errors, menus, my_chats, start
from bot.logging_config import setup_logging
from bot.middleware import DbSessionMiddleware, ErrorMiddleware
from bot.services.ai_service import ai_service

logger = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="start", description="Запустить бота"),
    BotCommand(command="help", description="Как это работает"),
    BotCommand(command="cancel", description="Отменить текущее действие"),
    BotCommand(command="premium", description="Информация о Premium"),
    BotCommand(command="admin", description="Админ-панель"),
]


def build_dispatcher() -> Dispatcher:
    """Собрать Dispatcher с роутерами в правильном порядке.

    Порядок важен: ``errors`` подключается последним и ловит
    всё, что не обработано остальными роутерами.
    """
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Порядок роутеров
    dp.include_router(start.router)
    dp.include_router(menus.router)
    dp.include_router(create.router)
    dp.include_router(editor.router)
    dp.include_router(my_chats.router)
    dp.include_router(ai.router)
    dp.include_router(admin.router)
    dp.include_router(errors.router)  # catch-all — строго последний

    # Middleware: сначала ловим исключения, затем открываем сессию
    dp.message.middleware(ErrorMiddleware())
    dp.callback_query.middleware(ErrorMiddleware())
    dp.message.middleware(DbSessionMiddleware())
    dp.callback_query.middleware(DbSessionMiddleware())
    return dp


async def on_startup(bot: Bot) -> None:
    """Действия при запуске: команды, очистка старых событий."""
    settings.setup_dirs()
    await create_all()

    # Прогрев шрифтов: находим файлы один раз при старте
    fonts = get_font_manager()
    logger.info("Шрифты: %s", fonts.info())

    try:
        await bot.set_my_commands(COMMANDS)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Не удалось обновить команды бота: %s", exc)

    from bot.database.engine import session_scope

    async with session_scope() as session:
        removed = await UsageRepository(session).purge_old(30)
        if removed:
            logger.info("Очищено старых событий: %s", removed)

    logger.info("=" * 58)
    logger.info("  Telegram Chat Constructor Bot запущен")
    logger.info("  AI: %s", ai_service.status_text())
    logger.info("  Администраторы: %s", len(settings.admin_ids))
    logger.info("  БД: %s", settings.db_file)
    logger.info("=" * 58)


async def on_shutdown() -> None:
    """Корректное завершение: закрываем БД."""
    logger.info("Остановка бота…")
    await dispose_engine()


async def main() -> int:
    """Запуск бота с устойчивостью к сетевым сбоям.

    Раньше любая исключительная ситуация приводила к ``return 1``, и платформа
    перезапускала контейнер — бот «падал» каждые несколько секунд. Теперь
    сетевые ошибки и конфликт getUpdates обрабатываются повторными попытками
    с нарастающей паузой, и процесс остаётся жив.
    """
    setup_logging()
    try:
        settings.validate_runtime()
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 1

    # Сессия с прокси — нужна, если api.telegram.org недоступен из сети хостинга
    session = None
    if settings.telegram_proxy:
        try:
            from aiogram.client.session.aiohttp import AiohttpSession

            # aiogram работает поверх aiohttp; для socks5 нужен aiohttp-socks
            import aiohttp_socks  # noqa: F401

            session = AiohttpSession(proxy=settings.telegram_proxy)
            logger.info(
                "Используется прокси %s:%s",
                settings.telegram_proxy_host,
                settings.telegram_proxy_port,
            )
        except ImportError:
            logger.error(
                "Указан TELEGRAM_PROXY, но пакет aiohttp-socks не установлен. "
                "Выполните: pip install aiohttp-socks"
            )
            return 1
        except Exception as exc:  # noqa: BLE001
            logger.error("Не удалось настроить прокси: %s: %s",
                         type(exc).__name__, exc)
            return 1

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode="HTML", link_preview_is_disabled=True),
        session=session,
    )
    dp = build_dispatcher()
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Платформа (Traefik) ждёт HTTP на порту из переменной PORT.
    # Для бота на long polling он не нужен, но без него домен отдаёт 502.
    start_health_server()
    set_status(bot="running")

    # Ошибки, при которых бессмысленно сразу падать: сеть отвалилась,
    # Telegram временно недоступен, другой экземпляр бота забрал polling.
    RETRYABLE = (
        TelegramNetworkError,
        TelegramServerError,
        TelegramConflictError,
        RestartingTelegram,
        asyncio.TimeoutError,
    )

    attempt = 0
    try:
        while True:
            try:
                if attempt:
                    # Рост паузы: 2, 4, 8, 16, 32, 60, 60…
                    # Раньше min(attempt, 5) навсегда застревал на 32 с,
                    # хотя внешний min(60, …) обещал потолок 60.
                    delay = min(60, 2 ** min(attempt, 6))
                    logger.warning(
                        "Повтор через %s с (попытка %s).", delay, attempt + 1
                    )
                    await asyncio.sleep(delay)
                await bot.delete_webhook(drop_pending_updates=True)
                set_status(telegram="connected")
                logger.info("Polling запущен. Нажмите Ctrl+C для остановки.")
                attempt = 0
                await dp.start_polling(
                    bot, allowed_updates=dp.resolve_used_update_types()
                )
                break
            except (KeyboardInterrupt, SystemExit):
                raise
            except RETRYABLE as exc:
                attempt += 1
                set_status(telegram=f"error: {type(exc).__name__}")
                # Не засоряем лог сотнями одинаковых строк: подробно пишем
                # первые попытки, дальше — краткое напоминание с интервалом.
                if attempt <= 3 or attempt % 10 == 0:
                    logger.error(
                        "Сбой соединения с Telegram (попытка %s): %s: %s",
                        attempt, type(exc).__name__, exc,
                    )
                if attempt == 5:
                    logger.error(
                        "Telegram API недоступен из этой сети уже 5 попыток подряд. "
                        "Бот продолжает работать и подключится сам, как только сеть "
                        "станет доступна. Если это не так — укажите прокси: "
                        "TELEGRAM_PROXY=socks5://логин:пароль@хост:порт"
                    )
            except Exception as exc:  # noqa: BLE001
                # Непредвиденная ошибка: логируем с трассировкой, но процесс
                # не убиваем — платформа не должна перезапускать контейнер
                # в бесконечном цикле, оставляя бота без сообщений об ошибке.
                attempt += 1
                logger.exception("Непредвиденная ошибка при работе polling")
                print(f"Ошибка работы бота: {type(exc).__name__}: {exc}", file=sys.stderr)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Получен сигнал остановки")
    finally:
        try:
            await dp.shutdown()
        except Exception:  # noqa: BLE001 # pragma: no cover
            pass
        try:
            await bot.session.close()
        except Exception:  # noqa: BLE001 # pragma: no cover
            pass
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
