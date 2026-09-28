"""Стартовый скрипт контейнера.

Проверяет окружение (токен, шрифты, БД) и только потом запускает бота —
так ошибки конфигурации видны сразу в логах платформы, а не молча.
"""

from __future__ import annotations

import os
import subprocess
import sys


def log(message: str) -> None:
    print(f"[start] {message}", flush=True)


def check_token() -> bool:
    token = (os.environ.get("BOT_TOKEN") or "").strip()
    if not token:
        log("ОШИБКА: BOT_TOKEN не задан. Задайте переменную окружения BOT_TOKEN.")
        return False
    if ":" not in token or len(token) < 30:
        log("ОШИБКА: BOT_TOKEN выглядит некорректно (ожидается формат 123456:AA...).")
        return False
    log("BOT_TOKEN найден")
    return True


def check_fonts() -> None:
    try:
        from bot.generators.fonts import get_font_manager

        manager = get_font_manager()
        info = manager.info()
        log(f"Шрифты: {info}")
        for warning in manager.warnings:
            log(f"ВНИМАНИЕ: {warning}")
    except Exception as exc:  # noqa: BLE001
        log(f"Не удалось прочитать шрифты: {exc}")


def check_data_dir() -> bool:
    db_path = os.environ.get("DB_PATH", "/app/data/bot.sqlite3")
    directory = os.path.dirname(db_path) or "/app/data"
    try:
        os.makedirs(directory, exist_ok=True)
        media = os.path.join(directory, "media")
        renders = os.path.join(directory, "renders")
        os.makedirs(media, exist_ok=True)
        os.makedirs(renders, exist_ok=True)
        log(f"Каталог данных готов: {directory}")
        return True
    except OSError as exc:
        log(f"ОШИБКА: нет доступа к каталогу {directory}: {exc}")
        return False


def run_selfcheck() -> None:
    """Прогон самопроверки рендерера (не блокирует запуск)."""
    try:
        proc = subprocess.run(
            [sys.executable, "check.py"],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        for line in (proc.stdout or "").splitlines():
            if "[FAIL]" in line or "ИТОГО" in line:
                log(line.strip())
        if proc.returncode != 0:
            log("Самопроверка выявила проблемы — см. логи выше.")
    except subprocess.TimeoutExpired:
        log("Самопроверка не успела завершиться за 5 минут, пропускаем.")
    except Exception as exc:  # noqa: BLE001
        log(f"Самопроверка пропущена: {exc}")


def main() -> int:
    log("=" * 54)
    log("Telegram Chat Constructor Bot — запуск в контейнере")
    log("=" * 54)

    if not check_token():
        return 1
    if not check_data_dir():
        return 1

    check_fonts()
    run_selfcheck()

    log("Запускаю бота…")
    try:
        from bot.main import main as bot_main
        import asyncio

        return asyncio.run(bot_main())
    except Exception as exc:  # noqa: BLE001
        log(f"КРИТИЧЕСКАЯ ОШИБКА: {type(exc).__name__}: {exc}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
