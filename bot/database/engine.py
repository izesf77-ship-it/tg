"""Движок SQLAlchemy и фабрика сессий (aiosqlite)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from bot.config import settings

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _is_memory(url: str) -> bool:
    return ":memory:" in url or "mode=memory" in url


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_connection, connection_record) -> None:
    """Настройки SQLite при каждом подключении.

    WAL-режим позволяет читать и писать одновременно, а busy_timeout
    заставляет ждать освобождения блокировки вместо мгновенной ошибки
    «database is locked».
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


def get_engine() -> AsyncEngine:
    """Ленивое создание движка."""
    global _engine
    if _engine is not None:
        return _engine

    settings.setup_dirs()
    url = f"sqlite+aiosqlite:///{settings.db_file.as_posix()}"

    kwargs: dict = {"echo": False, "future": True}
    if _is_memory(url):
        kwargs["poolclass"] = StaticPool
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_pre_ping"] = True
        # WAL + busy_timeout снимают «database is locked»: aiogram
        # обрабатывает апдейты параллельно, и без этого две сессии
        # конфликтуют при записи.
        kwargs["connect_args"] = {"timeout": 30}

    _engine = create_async_engine(url, **kwargs)
    logger.info("БД: %s", settings.db_file)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _sessionmaker


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Контекстный менеджер сессии с корректным rollback."""
    factory = get_sessionmaker()
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def create_all() -> None:
    """Создать все таблицы (идемпотентно)."""
    from bot.models import Base

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Схема базы данных готова")


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        logger.info("Соединение с БД закрыто")
    _engine = None
    _sessionmaker = None


# Алиас для удобства
close_db = dispose_engine


__all__ = [
    "get_engine",
    "get_sessionmaker",
    "session_scope",
    "create_all",
    "dispose_engine",
    "close_db",
    "AsyncSession",
]
