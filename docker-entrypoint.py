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


async def check_telegram(bot_token: str) -> bool:
    """Проверить токен реальным вызовом getMe.

    Разделяет две принципиально разные причины падения, которые по логам
    невозможно отличить:
      * 401 Unauthorized — токен неверный;
      * сетевая ошибка — нет доступа к api.telegram.org.
    """
    import httpx

    url = f"https://api.telegram.org/bot{bot_token}/getMe"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
    except Exception as exc:  # noqa: BLE001
        log(f"СЕТЬ: нет доступа к api.telegram.org — {type(exc).__name__}: {exc}")
        log("  Если бот запущен за рубежом или в сети с ограничениями, "
            "укажите прокси: TELEGRAM_PROXY=socks5://user:pass@host:port")
        return False

    if response.status_code == 401:
        log("ОШИБКА: Telegram отклонил токен (401 Unauthorized).")
        log("  Проверьте, что BOT_TOKEN указан верно и без лишних пробелов.")
        return False
    if response.status_code != 200:
        log(f"ПРЕДУПРЕЖДЕНИЕ: getMe вернул HTTP {response.status_code}")
        return True
    try:
        username = response.json().get("result", {}).get("username", "?")
    except Exception:  # noqa: BLE001 # pragma: no cover
        username = "?"
    log(f"Токен принят Telegram, бот: @{username}")
    return True


def run_selfcheck() -> None:
    """Прогон самопроверки рендерера (не блокирует запуск).

    В контейнере отключается по умолчанию: полный прогон занимает ~20 секунд,
    а при каждом рестарте это существенно задерживает поднятие бота.
    Включается переменной окружения RUN_SELFCHECK=1.
    """
    if (os.environ.get("RUN_SELFCHECK") or "").strip().lower() not in ("1", "true", "yes"):
        log("Самопроверка пропущена (включается RUN_SELFCHECK=1)")
        return
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
    import asyncio

    log("=" * 54)
    log("Telegram Chat Constructor Bot — запуск в контейнере")
    log("=" * 54)

    token = (os.environ.get("BOT_TOKEN") or "").strip()
    if not token:
        log("ОШИБКА: BOT_TOKEN не задан. Задайте переменную окружения BOT_TOKEN.")
        return 1
    if ":" not in token or len(token) < 30:
        log("ОШИБКА: BOT_TOKEN выглядит некорректно (ожидается формат 123456:AA...).")
        return 1
    log("BOT_TOKEN найден")

    if not check_data_dir():
        return 1

    # Проверка связи с Telegram: отличает неверный токен от недоступной сети
    try:
        if not asyncio.run(check_telegram(token)):
            log("Запуск прерван: Telegram API недоступен или токен отклонён.")
            return 1
    except Exception as exc:  # noqa: BLE001 # pragma: no cover
        log(f"Проверку Telegram пропускаю: {type(exc).__name__}: {exc}")

    check_fonts()
    run_selfcheck()

    log("Запускаю бота…")
    try:
        from bot.main import main as bot_main

        return asyncio.run(bot_main())
    except Exception as exc:  # noqa: BLE001
        log(f"КРИТИЧЕСКАЯ ОШИБКА: {type(exc).__name__}: {exc}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
