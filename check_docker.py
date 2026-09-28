"""Проверка Docker-конфигурации без запуска Docker.

Проверяет, что все пути из инструкций COPY существуют, что файлы
перечислены в .dockerignore и что конфигурация логически непротиворечива.

Запуск:  python check_docker.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

DOCKERFILE = ROOT / "Dockerfile"
COMPOSE = ROOT / "docker-compose.yml"
DOCKERIGNORE = ROOT / ".dockerignore"
ENTRYPOINT = ROOT / "docker-entrypoint.py"

PROBLEMS: list = []
OKS: list = []


def ok(message: str) -> None:
    OKS.append(message)
    print(f"  [OK]   {message}")


def fail(message: str) -> None:
    PROBLEMS.append(message)
    print(f"  [FAIL] {message}")


def warn(message: str) -> None:
    print(f"  [WARN] {message}")


def main() -> int:
    print("=" * 62)
    print("  ПРОВЕРКА DOCKER-КОНФИГУРАЦИИ")
    print("=" * 62)

    for path in (DOCKERFILE, COMPOSE, DOCKERIGNORE, ENTRYPOINT):
        if path.exists():
            ok(f"{path.name} существует")
        else:
            fail(f"{path.name} НЕ НАЙДЕН")

    if DOCKERFILE.exists():
        check_dockerfile(DOCKERFILE)
    if DOCKERIGNORE.exists():
        check_dockerignore()
    if COMPOSE.exists():
        check_compose()
    if ENTRYPOINT.exists():
        check_entrypoint()
    check_project()

    print("\n" + "=" * 62)
    print(f"  ИТОГО: успешно {len(OKS)}, провалено {len(PROBLEMS)}")
    if PROBLEMS:
        print("\n  Проблемы:")
        for problem in PROBLEMS:
            print(f"    x {problem}")
    print("=" * 62)
    return 0 if not PROBLEMS else 1


def check_user_order(text: str) -> None:
    """Пользователь должен создаваться раньше, чем на него ссылается chown.

    Регрессия: chown -R appuser:appuser шёл ДО useradd, и сборка падала с
    «chown: appuser: No such file or user».
    """
    # Работаем только с финальным этапом — там, где реально создаётся пользователь.
    froms = [m.start() for m in re.finditer(r"^FROM\s", text, re.MULTILINE | re.IGNORECASE)]
    if not froms:
        return
    stage = text[froms[-1]:]
    # Комментарии вырезаем: в них слова «chown»/«useradd» встречаются как
    # примеры в тексте и дают ложные срабатывания.
    stage = "\n".join(
        line for line in stage.splitlines() if not line.lstrip().startswith("#")
    )

    user_match = re.search(r"^USER\s+(\S+)", stage, re.MULTILINE)
    if not user_match:
        return  # финальный этап работает от root — chown не требуется
    user_name = user_match.group(1)
    creates = re.search(r"(useradd|adduser|groupadd)[^\n]*" + re.escape(user_name), stage)
    chowns = re.search(r"chown[^\n]*" + re.escape(user_name), stage)

    if creates is None:
        fail(f"Пользователь {user_name} используется, но не создаётся в финальном этапе")
        return
    ok(f"Пользователь {user_name} создаётся в финальном этапе")

    if chowns is None:
        ok(f"chown для {user_name} не используется — конфликта прав нет")
    elif creates.start() < chowns.start():
        ok(f"Порядок верен: {user_name} создан раньше chown")
    else:
        fail(f"chown для {user_name} идёт ДО его создания — сборка упадёт")


def check_dockerfile(path: Path) -> None:
    """Проверки Dockerfile."""
    text = path.read_text(encoding="utf-8")

    stages = re.findall(r"^FROM\s+(\S+)(?:\s+AS\s+(\S+))?",
                       text, re.MULTILINE | re.IGNORECASE)
    if stages:
        names = ", ".join(s[1] or s[0] for s in stages)
        ok(f"FROM найдено, этапов: {len(stages)} ({names})")
    else:
        fail("Нет инструкции FROM")

    for keyword, message in (
        ("HEALTHCHECK", "Нет HEALTHCHECK"),
        ("VOLUME", "Нет VOLUME — данные не переживут пересборку"),
        ("EXPOSE", "Нет EXPOSE — платформа не найдёт порт для прокси"),
    ):
        if keyword in text:
            ok(f"{keyword} присутствует")
        else:
            fail(message)

    if "/health" in text:
        ok("HEALTHCHECK проверяет HTTP-эндпоинт /health")
    else:
        fail("HEALTHCHECK не использует /health — порт не будет отвечать")

    if re.search(r"^USER\s+(?!root)", text, re.MULTILINE):
        ok("USER задан (контейнер работает не от root)")
    else:
        fail("Не задан непривилегированный USER")

    check_user_order(text)

    if "PIP_NO_CACHE_DIR" in text:
        ok("Кэш pip отключён")
    else:
        fail("Кэш pip не отключён")

    if "fonts-noto-color-emoji" in text and "fonts-dejavu" in text:
        ok("Системные шрифты (кириллица + emoji) устанавливаются")
    else:
        fail("Не установлены шрифты — русский текст и emoji могут не работать")

    if "chmod" in text or "ENTRYPOINT" in text or "CMD" in text:
        ok("Точка входа задана (ENTRYPOINT/CMD)")
    else:
        fail("Не задана точка входа")

    # --- Пути из COPY должны существовать ---
    # Учитываются только локальные источники: инструкции вида
    # COPY --from=builder /wheels /wheels ссылаются на другой этап.
    print("\n  Проверка путей COPY:")
    for match in re.finditer(r"^COPY\s+([^\n]+?)\s+(\S+)\s*$", text, re.MULTILINE):
        parts = match.group(1).split()
        if parts and parts[0].startswith("--from="):
            ok(f"COPY {' '.join(parts)} -> из другого этапа, пропускаем")
            continue
        for source in parts:
            if ":" in source:
                continue
            local = ROOT / source.rstrip("/")
            if source.endswith("/"):
                if local.is_dir():
                    count = len(list(local.iterdir()))
                    ok(f"COPY {source} -> каталог есть ({count} объект(ов))")
                else:
                    fail(f"COPY {source} -> каталог НЕ НАЙДЕН: {local}")
            elif local.exists():
                ok(f"COPY {source} -> найден ({local.stat().st_size} байт)")
            else:
                fail(f"COPY {source} -> ФАЙЛ НЕ НАЙДЕН: {local}")


def check_dockerignore() -> None:
    """Проверки .dockerignore."""
    lines = DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
    ignore_text = "\n".join(
        line.strip() for line in lines if line.strip() and not line.strip().startswith("#")
    )
    for required in (".env", "data/", "__pycache__/", ".venv/"):
        if required in ignore_text:
            ok(f".dockerignore исключает {required}")
        else:
            fail(f".dockerignore НЕ исключает {required}")
    if "output/" in ignore_text:
        ok(".dockerignore исключает output/")
    else:
        fail(".dockerignore не исключает output/")
    if "*.ttf" in ignore_text:
        ok(".dockerignore исключает пользовательские шрифты (*.ttf)")
    else:
        warn(".dockerignore не исключает *.ttf — шрифты попадут в образ")


def check_compose() -> None:
    """Проверки docker-compose.yml."""
    text = COMPOSE.read_text(encoding="utf-8")
    for needle, message in (
        ("bot:", "нет сервиса bot"),
        ("env_file", "не подключён .env"),
        ("/app/data", "нет volume для данных"),
        ("restart:", "нет политики перезапуска"),
        ("healthcheck:", "нет healthcheck"),
    ):
        if needle in text:
            ok(f"docker-compose.yml: {needle} на месте")
        else:
            fail(f"docker-compose.yml: {message}")


def check_entrypoint() -> None:
    """Проверки стартового скрипта."""
    import ast

    text = ENTRYPOINT.read_text(encoding="utf-8")
    try:
        ast.parse(text)
        ok("docker-entrypoint.py: синтаксис корректен")
    except SyntaxError as exc:
        fail(f"docker-entrypoint.py: ошибка синтаксиса: {exc}")
    if "BOT_TOKEN" in text:
        ok("docker-entrypoint.py: проверяет BOT_TOKEN")
    else:
        fail("docker-entrypoint.py: нет проверки BOT_TOKEN")
    if "bot.main" in text:
        ok("docker-entrypoint.py: запускает bot.main")
    else:
        fail("docker-entrypoint.py: не запускает bot.main")


def check_project() -> None:
    """Проверки файлов проекта."""
    req = ROOT / "requirements.txt"
    if req.exists():
        text = req.read_text(encoding="utf-8").lower()
        for package in ("aiogram", "sqlalchemy", "aiosqlite", "pillow",
                        "pydantic", "pydantic-settings", "python-dotenv", "httpx"):
            if package in text:
                ok(f"requirements.txt: {package}")
            else:
                fail(f"requirements.txt НЕ содержит {package}")
        if "aiohttp-socks" in text:
            ok("requirements.txt: aiohttp-socks (поддержка прокси)")
        else:
            warn("requirements.txt без aiohttp-socks — TELEGRAM_PROXY не заработает")

    fonts_dir = ROOT / "fonts"
    if fonts_dir.is_dir():
        files = list(fonts_dir.glob("*.ttf")) + list(fonts_dir.glob("*.otf"))
        if files:
            ok(f"fonts/: {len(files)} шрифт(ов): {', '.join(f.name for f in files[:4])}")
        else:
            warn("fonts/ пуст — будут использованы системные шрифты из образа")
    if (fonts_dir / "README.txt").exists():
        ok("fonts/README.txt: инструкция на месте")

    if (ROOT / ".env.example").exists():
        ok(".env.example существует")
    else:
        fail(".env.example НЕ НАЙДЕН")
    if (ROOT / ".env").exists():
        warn(".env есть в проекте — убедитесь, что он НЕ попадает в Git")


if __name__ == "__main__":
    sys.exit(main())
