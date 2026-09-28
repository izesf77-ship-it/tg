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
    """Каталог данных должен существовать и быть доступным НА ЗАПИСЬ.

    Частая проблема на хостингах: volume монтируется от root, и непривилегированный
    пользователь не может писать в /app/data. Здесь это выявляется заранее и
    выводится понятная подсказка.
    """
    db_path = os.environ.get("DB_PATH", "/app/data/bot.sqlite3")
    directory = os.path.dirname(db_path) or "/app/data"
    try:
        os.makedirs(directory, exist_ok=True)
        for name in ("media", "renders"):
            os.makedirs(os.path.join(directory, name), exist_ok=True)
    except OSError as exc:
        log(f"ОШИБКА: нет доступа к каталогу {directory}: {exc}")
        _log_permission_hint(directory)
        return False

    # Проверка реальной возможности записи (права каталога != возможность писать
    # при запрещённом SELinux/AppArmor или read-only mount).
    probe = os.path.join(directory, ".write_probe")
    try:
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("ok")
        os.remove(probe)
    except OSError as exc:
        log(f"ОШИБКА: каталог {directory} доступен только для чтения: {exc}")
        _log_permission_hint(directory)
        return False

    log(f"Каталог данных готов и доступен для записи: {directory}")
    return True


def _log_permission_hint(directory: str) -> None:
    """Подсказка для администратора хостинга."""
    try:
        uid, gid = os.getuid(), os.getgid()
    except AttributeError:  # pragma: no cover — не POSIX
        return
    log("ПОДСКАЗКА: каталог данных смонтирован от другого пользователя.")
    log(f"  контейнер работает как uid={uid}, gid={gid}, каталог: {directory}")
    log("  Исправьте владельца на хосте:  chown -R 10001:10001 <путь-к-volume>")
    log('  Либо запустите контейнер от root: добавьте user: "0:0" в compose')


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
