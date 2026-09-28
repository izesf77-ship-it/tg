"""Точка входа: сборка Dispatcher, роутеров и запуск polling."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.config import settings
from bot.database.engine import create_all, dispose_engine
from bot.database.repositories import UsageRepository
from bot.generators.fonts import get_font_manager
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
    """Запуск бота."""
    setup_logging()
    try:
        settings.validate_runtime()
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 1

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode="HTML", link_preview_is_disabled=True),
    )
    dp = build_dispatcher()
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Polling запущен. Нажмите Ctrl+C для остановки.")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Получен сигнал остановки")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Критическая ошибка при запуске polling")
        print(f"Ошибка запуска: {exc}", file=sys.stderr)
        return 1
    finally:
        await dp.shutdown()
        try:
            await bot.session.close()
        except Exception:  # noqa: BLE001 # pragma: no cover
            pass
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
