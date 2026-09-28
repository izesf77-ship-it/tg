"""Проверка прокси для Telegram — запускается без кавычек и капризов PowerShell.

Запуск:
    python check_proxy.py socks5://login:password@host:port
    python check_proxy.py http://host:8080
    python check_proxy.py 1.2.3.4:1080

Скрипт ничего не меняет в системе: только читает настройки и делает
один запрос к Telegram, чтобы проверить, работает ли прокси.
"""

from __future__ import annotations

import asyncio
import sys

# Заведомо неверный токен: правильный ответ Telegram — 401.
# Это доказывает, что прокси дошёл до сервера и канал работает.
TEST_URL = "https://api.telegram.org/bot0:AA/getMe"


def normalize(raw: str) -> str:
    """Привести пользовательский ввод к полноценному URL прокси."""
    value = (raw or "").strip().strip("'\"")
    if not value:
        raise SystemExit("Укажите прокси, например: python check_proxy.py socks5://user:pass@host:1080")
    if "://" not in value:
        value = f"socks5://{value}"
    return value


def mask(url: str) -> str:
    """Скрыть логин и пароль, чтобы не светить их на экране и в истории."""
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(url)
    if not parsed.username and not parsed.password:
        return url
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunparse((parsed.scheme, f"***:***@{host}", "", "", "", ""))


def explain(exc: BaseException) -> str:
    """Перевести исключение в понятное объяснение."""
    name = type(exc).__name__
    text = str(exc)
    if name == "ImportError" and "socksio" in text:
        return "не установлен socksio — выполните: pip install socksio"
    if "Malformed reply" in text or "Malformed" in text:
        return "порт занят НЕ прокси (частая ошибка — перепутан порт)"
    if "ConnectTimeout" in name or "Connect timeout" in text:
        return "прокси не отвечает: неверный адрес, порт или прокси выключен"
    if "Authentication" in text or "auth" in text.lower():
        return "неверный логин или пароль"
    if "Name or service not known" in text or "getaddrinfo" in text:
        return "не удалось разрешить имя хоста — проверьте адрес"
    return f"{name}: {text[:160]}"


async def probe(url: str) -> int:
    import httpx

    print("=" * 60)
    print("Проверка прокси:", mask(url))
    print("=" * 60)
    print(f"Запрос к {TEST_URL} …\n")

    try:
        async with httpx.AsyncClient(proxy=url, timeout=15.0) as client:
            response = await client.get(TEST_URL)
    except Exception as exc:  # noqa: BLE001
        print("НЕ РАБОТАЕТ")
        print("Причина:", explain(exc))
        print("\nЧто делать:")
        print("  * проверьте порт и адрес в личном кабинете провайдера;")
        print("  * убедитесь, что у прокси есть логин и пароль;")
        print("  * попробуйте другую схему: http:// вместо socks5://")
        return 1

    code = response.status_code
    if code == 401:
        print("ПРОКСИ РАБОТАЕТ")
        print("Telegram ответил 401 на заведомо неверный токен — канал исправен.")
        print("Можно указывать в переменных окружения:")
        print(f"  TELEGRAM_PROXY={mask(url)}")
        return 0

    if code == 200:
        print("ПРОКСИ РАБОТАЕТ (Telegram ответил 200)")
        return 0

    print(f"Прокси отвечает, но неожиданный код: {code}")
    print("Посмотрите начало ответа:", response.text[:200])
    return 1


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        print("Примеры:")
        print("  python check_proxy.py socks5://login:password@1.2.3.4:1080")
        print("  python check_proxy.py 1.2.3.4:1080")
        return 0
    return asyncio.run(probe(normalize(sys.argv[1])))


if __name__ == "__main__":
    sys.exit(main())
