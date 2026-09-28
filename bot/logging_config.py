"""Единая настройка логирования.

Правила:
* токены, ключи API и содержимое переписок НЕ логируются;
* в консоль — кратко, в файл — подробно (с ротацией по размеру).
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from bot.config import settings

_CONSOLE_FMT = "%(levelname)-8s %(asctime)s | %(name)-22s | %(message)s"
_FILE_FMT = "%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s"

# Эти данные никогда не попадают в логи
SENSITIVE_KEYS = (
    "bot_token",
    "token",
    "api_key",
    "openrouter_api_key",
    "password",
    "authorization",
)


class _RedactFilter(logging.Filter):
    """Маскирует значения токенов/ключей, если они случайно попали в сообщение."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            return True
        if any(k in msg.lower() for k in SENSITIVE_KEYS):
            record.msg = "<redacted sensitive log entry>"
            record.args = ()
        return True


_configured = False


def setup_logging(level: str | None = None) -> None:
    global _configured
    if _configured:
        return

    root = logging.getLogger()
    root.setLevel(getattr(logging, (level or settings.log_level), logging.INFO))

    for handler in list(root.handlers):
        root.removeHandler(handler)

    console = logging.StreamHandler(stream=sys.stdout)
    console.setLevel(root.level)
    console.setFormatter(logging.Formatter(_CONSOLE_FMT, datefmt="%H:%M:%S"))
    console.addFilter(_RedactFilter())
    root.addHandler(console)

    log_file: Path | None = settings.log_file_path
    if log_file:
        try:
            file_handler = logging.handlers.RotatingFileHandler(
                log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(_FILE_FMT))
            file_handler.addFilter(_RedactFilter())
            root.addHandler(file_handler)
        except OSError as exc:  # pragma: no cover - depends on FS
            root.warning("Не удалось открыть файл логов %s: %s", log_file, exc)

    # Сторонние библиотеки — тише
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)


__all__ = ["setup_logging", "get_logger"]
