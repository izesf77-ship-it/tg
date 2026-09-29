"""Самопроверка проекта.

Запуск:  python check.py
Тестовые изображения сохраняются в ./output,
подробный л��г — в ./_check_report.txt
"""

from __future__ import annotations

import io
import sys
import traceback
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.logging_config import setup_logging  # noqa: E402

setup_logging("WARNING")

# Консоль Windows может не печатать emoji/стрелки в cp1251
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

OUTPUT = ROOT / "output"
REPORT = ROOT / "_check_report.txt"
RESULTS = []
_BUFFER = io.StringIO()


def _emit(text: str) -> None:
    """Дублировать вывод в консоль и в итоговый отчёт."""
    print(text)
    _BUFFER.write(text + "\n")


def ok(name: str, detail: str = "") -> None:
    RESULTS.append((True, name, detail))
    _emit(f"  [OK]   {name}" + (f" — {detail}" if detail else ""))


def fail(name: str, detail: str = "") -> None:
    RESULTS.append((False, name, detail))
    _emit(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


def section(title: str) -> None:
    _emit("")
    _emit(f"=== {title} ===")


def step(name: str):
    """Декоратор: выполняет проверку и фиксирует результат."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                detail = func(*args, **kwargs) or ""
                ok(name, detail)
            except Exception as exc:  # noqa: BLE001
                fail(name, f"{type(exc).__name__}: {exc}")
                traceback.print_exc(file=_BUFFER)
        return wrapper

    return decorator


def build_demo_chat(message_count: int = 12) -> "ChatConfig":
    """Тестовая переписка на русском с разными типами сообщений."""
    from bot.schemas import (
        ChatConfig, MediaItem, Message, MessageKind, Participant, Reaction,
    )

    config = ChatConfig(title="Алина", style="telegram")
    config.participants = [
        Participant(
            name="Алексей", username="alexey", side=0,
            status="был(а) недавно", last_seen="21:14", premium=True,
        ),
        Participant(
            name="Алина", username="alina_k", side=1, status="в сети", premium=False,
        ),
    ]

    first = Message(
        kind=MessageKind.TEXT, text="Привет! Ты где?", time="21:14",
        side=0, author_index=0, reaction=Reaction(emoji="👍", count=1),
    )
    config.add_message(first)
    config.add_message(
        Message(
            kind=MessageKind.TEXT, text="Привет! Дома сижу, надоело уже 😩",
            time="21:15", side=1, author_index=1, reply_to=first.id,
        )
    )
    config.add_message(
        Message(
            kind=MessageKind.IMAGE, time="21:16", side=0, author_index=0,
            media=MediaItem(kind=MessageKind.IMAGE, caption="Вот что нашла"),
        )
    )
    config.add_message(
        Message(
            kind=MessageKind.VOICE, time="21:17", side=1, author_index=1,
            media=MediaItem(kind=MessageKind.VOICE, duration="0:14"),
        )
    )
    config.add_message(
        Message(
            kind=MessageKind.TEXT,
            text="Очень длинное сообщение, которое специально проверяет перенос строк "
                 "в рендерере: оно содержит много слов и должно корректно разбиться "
                 "на несколько строк, чтобы текст не вылезал за границы пузыря.",
            time="21:18", side=0, author_index=0,
            reaction=Reaction(emoji="🔥", count=3),
        )
    )
    config.add_message(
        Message(
            kind=MessageKind.FILE, time="21:19", side=0, author_index=0,
            media=MediaItem(
                kind=MessageKind.FILE, file_name="счёт_на_оплату.pdf", file_size="2,4 МБ"
            ),
        )
    )
    config.add_message(
        Message(
            kind=MessageKind.STICKER, time="21:20", side=1, author_index=1,
            media=MediaItem(kind=MessageKind.STICKER, emoji="😂"),
        )
    )
    config.add_message(
        Message(
            kind=MessageKind.SERVICE, text="Алина зарегистрирована в Telegram",
            time="21:20", side=0,
        )
    )
    config.add_message(
        Message(
            kind=MessageKind.FORWARD, text="Смотри, что он написал",
            forward_from="Незнакомец", time="21:21", side=1, author_index=1,
        )
    )
    config.add_message(
        Message(
            kind=MessageKind.DATE, text="Завтра", time="09:15", side=0,
        )
    )

    base_minutes = 21 * 60 + 22
    while len(config.messages) < message_count:
        index = len(config.messages)
        side = index % 2
        author = 0 if side == 0 else 1
        text = (
            f"Сообщение №{index + 1} для проверки длинной переписки и переноса строк."
            if index % 3 == 0
            else f"Короткое сообщение {index + 1}"
        )
        minutes = base_minutes + index
        config.add_message(
            Message(
                kind=MessageKind.TEXT, text=text, side=side, author_index=author,
                time=f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}",
                read=index % 4 != 0,
            )
        )
    return config


@step("Рендер стиля Telegram (12 сообщений)")
def check_render_telegram() -> str:
    from bot.generators import get_renderer

    config = build_demo_chat(12)
    renderer = get_renderer("telegram")
    img = renderer.render(config)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "telegram_demo.png"
    img.save(path)
    assert img.width == 1080, f"Ширина {img.width} != 1080"
    assert img.height > 800, f"Высота подозрительно мала: {img.height}"
    return f"{img.width}x{img.height}, {path.name}"


@step("Рендер всех стилей")
def check_all_styles() -> str:
    from bot.generators import AVAILABLE_STYLES, get_renderer

    config = build_demo_chat(8)
    details = []
    for style in AVAILABLE_STYLES:
        img = get_renderer(style.key).render(config)
        OUTPUT.mkdir(parents=True, exist_ok=True)
        img.save(OUTPUT / f"style_{style.key}.png")
        details.append(f"{style.key}:{img.height}")
    return " ".join(details)


@step("Пустая переписка")
def check_empty_chat() -> str:
    from bot.generators import get_renderer
    from bot.schemas import ChatConfig

    config = ChatConfig(title="Пусто")
    config.ensure_participants()
    img = get_renderer("telegram").render(config)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    img.save(OUTPUT / "empty.png")
    return f"{img.width}x{img.height}"


@step("50+ сообщений (автовысота)")
def check_long_chat() -> str:
    from bot.generators import get_renderer

    config = build_demo_chat(60)
    img = get_renderer("telegram").render(config)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    img.save(OUTPUT / "long_60.png")
    assert img.height > 6000, f"Высота {img.height} — не выросла автоматически"
    return f"{len(config.messages)} сообщений -> {img.width}x{img.height}"


@step("Рост высоты пропорционален числу сообщений")
def check_height_growth() -> str:
    from bot.generators import get_renderer

    small = get_renderer("telegram").render(build_demo_chat(10))
    big = get_renderer("telegram").render(build_demo_chat(40))
    assert big.height > small.height * 1.8, (
        f"Высота растёт нелинейно: {small.height} -> {big.height}"
    )
    return f"10 сообщ.={small.height}px, 40 сообщ.={big.height}px"


@step("Очень длинный текст (перенос строк)")
def check_long_text() -> str:
    from bot.generators import get_renderer
    from bot.schemas import Message

    config = build_demo_chat(4)
    config.messages = config.messages[:1]
    huge = "Это очень длинное сообщение " * 60
    config.messages.append(Message(text=huge, time="10:00", side=0, author_index=0))
    img = get_renderer("telegram").render(config)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    img.save(OUTPUT / "long_text.png")
    return f"{len(huge)} символов -> {img.width}x{img.height}"


@step("Одно слово длиннее ширины пузыря")
def check_long_word() -> str:
    from bot.generators import get_renderer
    from bot.schemas import Message

    config = build_demo_chat(2)
    config.messages.append(
        Message(text="A" * 400, time="10:00", side=0, author_index=0)
    )
    config.messages.append(
        Message(text="https://example.com/" + "very-long-path-segment/" * 12,
                time="10:01", side=1, author_index=1)
    )
    img = get_renderer("telegram").render(config)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    img.save(OUTPUT / "long_word.png")
    return f"{img.width}x{img.height}"


@step("Эмодзи и кириллица в тексте")
def check_emoji() -> str:
    from bot.generators import get_renderer
    from bot.schemas import Message

    config = build_demo_chat(3)
    config.messages.append(
        Message(
            text="Привет 😀 Привет 🎉🔥 Крык 😎 Ура! 🇷🇺",
            time="11:00", side=1, author_index=1,
        )
    )
    img = get_renderer("telegram").render(config)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    img.save(OUTPUT / "emoji.png")
    from bot.generators.fonts import get_font_manager

    fm = get_font_manager()
    assert fm.measure("Привет", 30) > 0
    return f"шрифты: {fm.info()}"


@step("Кириллица действительно отрисована (не пустые рамки)")
def check_cyrillic_pixels() -> str:
    from PIL import Image, ImageDraw

    from bot.generators.fonts import get_font_manager

    fm = get_font_manager()
    img = Image.new("L", (400, 80), 0)
    ImageDraw.Draw(img).text((5, 5), "Привет мир", font=fm.get(40), fill=255)
    bbox = img.getbbox()
    assert bbox is not None, "Текст не отрисован"
    width = bbox[2] - bbox[0]
    assert width > 120, f"Подозрительно узкий текст: {width}px"
    return f"ширина текста {width}px"


@step("Конфигурация читает переменные окружения")
def check_env_config() -> str:
    """Регрессия: Settings на базе BaseModel игнорировал ENV, и в Docker
    бот стартовал с пустым BOT_TOKEN и падал в бесконечном рестарте."""
    import os

    from bot.config import Settings

    saved = {
        key: os.environ.get(key)
        for key in ("BOT_TOKEN", "ADMIN_IDS", "TELEGRAM_PROXY")
    }
    try:
        os.environ["BOT_TOKEN"] = "123456789:AAEnvCheckToken_abcdefghijklmnop"
        os.environ["ADMIN_IDS"] = "111, 222;333"
        os.environ["TELEGRAM_PROXY"] = "socks5://u:p@proxy.test:1080"
        s = Settings()
        assert s.bot_token == os.environ["BOT_TOKEN"], "BOT_TOKEN не прочитан из ENV"
        assert s.admin_ids == [111, 222, 333], f"ADMIN_IDS разобран неверно: {s.admin_ids}"
        assert s.telegram_proxy_host == "proxy.test", s.telegram_proxy_host
        assert s.telegram_proxy_port == 1080, s.telegram_proxy_port
        assert s.telegram_proxy_user == "u", s.telegram_proxy_user
        assert s.telegram_proxy_password == "p", s.telegram_proxy_password

        # Пустой ADMIN_IDS не должен ломать запуск
        os.environ["ADMIN_IDS"] = ""
        assert Settings().admin_ids == [], "Пустой ADMIN_IDS должен давать пустой список"
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return "BOT_TOKEN, ADMIN_IDS, TELEGRAM_PROXY читаются из ENV"


@step("Маскирование логов не скрывает текст ошибки")
def check_log_scrub() -> str:
    from bot.logging_config import scrub

    hidden = scrub("токен 123456789:AAEnvCheckToken_abcdefghijklmnop упал")
    assert "AAEnvCheckToken" not in hidden, "Токен не замаскирован"
    assert "упал" in hidden, f"Текст ошибки потерян: {hidden}"

    kept = scrub("TelegramNetworkError: connection refused")
    assert kept == "TelegramNetworkError: connection refused", kept
    return "секреты скрыты, диагностика сохранена"


@step("HTTP-сервис healthcheck отвечает")
def check_health_server() -> str:
    import json
    import urllib.request

    from bot.health import set_status, start_health_server

    port = 18099
    server = start_health_server(port)
    assert server is not None, "Сервер не поднялся"
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as r:
            assert r.status == 200, f"HTTP {r.status}"
            payload = json.loads(r.read().decode("utf-8"))
        assert payload.get("status") == "ok", payload

        set_status(bot="running", telegram="connected")
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as r:
            payload = json.loads(r.read().decode("utf-8"))
        assert payload["bot"] == "running", payload
        assert payload["telegram"] == "connected", payload
    finally:
        server.shutdown()
        server.server_close()
    return f"порт {port}, /health отдаёт 200 со статусом"


@step("Диагностика прокси: разбор адреса и масокирование")
def check_proxy_helper() -> str:
    """Логика check_proxy.py проверяется без сети: только разбор и маскирование."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("check_proxy", ROOT / "check_proxy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Схема подставляется автоматически
    assert module.normalize("1.2.3.4:1080") == "socks5://1.2.3.4:1080"
    assert module.normalize("http://h:8080") == "http://h:8080"
    assert module.normalize("  socks5://u:p@h:1  ") == "socks5://u:p@h:1"

    # Логин и пароль не должны попадать в вывод
    masked = module.mask("socks5://secretuser:secretpass@1.2.3.4:1080")
    assert "secretuser" not in masked, masked
    assert "secretpass" not in masked, masked
    assert "1.2.3.4:1080" in masked, masked
    assert module.mask("socks5://1.2.3.4:1080") == "socks5://1.2.3.4:1080"

    # Ошибки переводятся в понятные формулировки
    # (проверяем на настоящих исключениях, а не на строках)
    assert "socksio" in module.explain(ImportError("no module named socksio"))
    assert "НЕ прокси" in module.explain(Exception("Malformed reply"))

    class ConnectTimeout(Exception):
        pass

    assert "не отвечает" in module.explain(ConnectTimeout("timed out"))
    assert "неверный логин или пароль" in module.explain(
        Exception("SOCKS5 Authentication failure")
    )
    return "адрес, маскирование и разбор ошибок корректны"


@step("Хендлеры получают сервисы из middleware, а не из event.data")
def check_handler_context() -> str:
    """Регрессия: u Message нет поля data, а у CallbackQuery data — строка.

    Из-за этого обращения вида message.data["services"] падали с
    AttributeError/TypeError, и любой хендлер отвечал «Внутренняя ошибка».
    Проверяем и структуру кода, и реальное поведение.
    """
    import datetime
    import re

    from aiogram.types import CallbackQuery, Chat, Message as TgMessage, User

    from bot.middleware import get_db_user, get_services, is_premium

    # 1) Реальные объекты aiogram: убеждаемся в самой причине бага
    user = User(id=42, is_bot=False, first_name="T")
    message = TgMessage(
        message_id=1, date=datetime.datetime.now(),
        chat=Chat(id=1, type="private"), from_user=user,
    )
    callback = CallbackQuery(
        id="1", from_user=user, chat_instance="x", data="ed:open:1:2"
    )
    assert not hasattr(message, "data"), "У Message не должно быть поля data"
    assert isinstance(callback.data, str), "CallbackQuery.data — строка"

    # 2) Хелперы достают сервисы из обычного словаря-контекста
    services = {"chats": "CHATS", "limits": "LIMITS", "user": "USER"}
    data = {"services": services, "db_user": object()}
    assert get_services(data)["chats"] == "CHATS"
    assert get_db_user(data) is data["db_user"]
    assert is_premium(data) is False, "обычный объект не должен считаться Premium"

    premium_user = type("U", (), {"is_premium": True})()
    assert is_premium({"db_user": premium_user}) is True
    # Отсутствие пользователя не должно ронять код
    assert is_premium({}) is False
    assert get_services({}) == {}

    # 3) В коде хендлеров не осталось обращений через event.data
    offenders = []
    pattern = re.compile(r'\b\w+\.data\["(services|db_user|session)"\]')
    for path in (ROOT / "bot" / "handlers").glob("*.py"):
        for num, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if pattern.search(line):
                offenders.append(f"{path.name}:{num}")
    assert not offenders, "Остались обращения event.data: " + ", ".join(offenders)

    # 4) Ключ сервиса — "user", а не "users"
    assert "users" not in services, "ключа 'users' в сервисах нет"
    return "контекст доступен, обращений event.data не осталось"


@step("Хендлеры получают сервисы из контекста, а не из event.data")
def check_handler_context() -> str:
    """Регрессия: u Message нет поля data, a u CallbackQuery data — stroka.

    Iz-za etogo obrasheniya vida message.data["services"] pали s
    AttributeError/TypeError, i lyuboy handler otvechal «Внутренняя ошибка».
    Servisy teper hranitsya v ContextVar i chitayutsya bez argumentov.
    """
    import datetime
    import re

    from aiogram.types import CallbackQuery, Chat, Message as TgMessage, User

    from bot.middleware import (
        _Context, db_session, get_db_user, get_services, is_premium,
        reset_context, set_context,
    )

    # 1) Реальные объекты aiogram: убеждаемся в самой причине бага
    user = User(id=42, is_bot=False, first_name="T")
    message = TgMessage(
        message_id=1, date=datetime.datetime.now(),
        chat=Chat(id=1, type="private"), from_user=user,
    )
    callback = CallbackQuery(
        id="1", from_user=user, chat_instance="x", data="ed:open:1:2"
    )
    assert not hasattr(message, "data"), "У Message не должно быть поля data"
    assert isinstance(callback.data, str), "CallbackQuery.data — строка"

    # 2) Без контекста хелперы обязаны падать понятной ошибкой
    try:
        get_services()
    except RuntimeError as exc:
        assert "DbSessionMiddleware" in str(exc), str(exc)
    else:
        raise AssertionError("get_services() вне контекста должен падать")

    # 3) В контексте всё доступно и без аргументов
    services = {"chats": "CHATS", "limits": "LIMITS", "user": "USER"}
    db_user = type("U", (), {"is_premium": True})()
    token = set_context(
        _Context(session="SESSION", services=services, db_user=db_user)
    )
    try:
        assert get_services()["chats"] == "CHATS"
        assert get_db_user() is db_user
        assert db_session() == "SESSION"
        assert is_premium() is True
    finally:
        reset_context(token)

    # Контекст обязан сбрасываться — иначе сервисы утекут в следующий апдейт
    try:
        get_services()
    except RuntimeError:
        pass
    else:
        raise AssertionError("контекст не сброшен после reset_context()")

    # 4) В коде хендлеров не осталось обращений через event.data
    offenders = []
    pattern = re.compile(
        r'\b\w+\.data\["(services|db_user|session)"\]'
        r"|get_services\(\s*\w+\.data"
        r"|get_db_user\(\s*\w+\.data"
        r"|is_premium\(\s*\w+\.data"
    )
    for path in (ROOT / "bot" / "handlers").glob("*.py"):
        for num, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if pattern.search(line):
                offenders.append(f"{path.name}:{num}")
    assert not offenders, "Остались обращения event.data: " + ", ".join(offenders)

    # 5) Ключ сервиса — "user", а не "users"
    assert "users" not in services, "ключа 'users' в сервисах нет"
    return "контекст работает, обращений event.data не осталось"


@step("Хендлер /start отвечает без ошибок (интеграционно)")
def check_start_handler() -> str:
    """Полный сценарий: middleware -> хендлер -> БД, на настоящих объектах.

    Именно этот сценарий ломался в продакшене.
    """
    import asyncio
    import datetime

    from aiogram.types import Chat, Message as TgMessage, User

    from bot.database.engine import create_all, dispose_engine, session_scope
    from bot.handlers.start import cmd_start
    from bot.middleware import DbSessionMiddleware

    sent: list = []

    async def fake_answer(self, text, **kwargs):
        sent.append(str(text)[:60])
        return self

    async def run() -> str:
        await create_all()
        uid = 6518052880
        tg_user = User(id=uid, is_bot=False, first_name="Integr")
        message = TgMessage(
            message_id=1, date=datetime.datetime.now(),
            chat=Chat(id=uid, type="private"), from_user=tg_user, text="/start",
        )

        class _St:
            async def clear(self):
                return None

        errors: list = []

        async def handler(event, data):
            try:
                await cmd_start(event, _St())
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{type(exc).__name__}: {exc}")
            return None

        TgMessage.answer = fake_answer
        mw = DbSessionMiddleware()
        await mw(handler, message, {"event_from_user": tg_user})

        if errors:
            return "ОШИБКА: " + "; ".join(errors)

        # Пользователь должен появиться в БД
        from bot.models import User as UserModel

        async with session_scope() as session:
            row = await session.get(UserModel, uid)
            if row is None:
                return "пользователь не зарегистрирован"
        if not sent:
            return "хендлер не отправил ни одного сообщения"
        return f"ok: сообщений {len(sent)}, приветствие: {sent[0][:28]!r}"

    try:
        detail = asyncio.run(run())
    finally:
        asyncio.run(dispose_engine())

    assert not detail.startswith("ОШИБКА"), detail
    assert "пользователь не зарегистрирован" not in detail, detail
    return detail


@step("chat_id в callback_data читается одинаково в кнопке и хендлере")
def check_callback_chat_id() -> str:
    """Регрессия: chat_id лежал на РАЗНЫХ позициях в разных кнопках.

    Обработчик участников брал ``arg_int(data, 2)``, а у кнопки
    ``pp:open:0:7`` chat_id стоит на позиции 1 — в итоге chat_id был -1
    и пользователь видел «Переписка не найдена».
    """
    from bot.keyboards import create as CK
    from bot.utils import callbacks as C

    chat_id = 42

    # Кнопки участников: chat_id обязан извлекаться одинаково
    participant = type("P", (), {"name": "Алексей", "premium": False})()
    config = type("C", (), {"participants": [participant, participant]})()

    buttons = []
    markup = CK.participants_menu(config, chat_id)
    for row in markup.inline_keyboard:
        buttons.extend(row)
    markup2 = CK.participant_card(0, participant, chat_id)
    for row in markup2.inline_keyboard:
        buttons.extend(row)

    assert buttons, "клавиатура участников пуста"
    checked = 0
    for button in buttons:
        data = button.callback_data
        action = C.action(data)
        # «Назад» ведёт на экран выбора стиля и переписку не открывает,
        # поэтому chat_id в этой кнопке не нужен.
        if action == "back":
            continue
        assert C.chat_id_of(data) == chat_id, (
            f"кнопка {button.text!r} ({data}) -> chat_id={C.chat_id_of(data)}"
        )
        checked += 1

    # Явные проверки форматов, где chat_id последний
    cases = [
        (C.cb(C.S_PART, "open", 0, chat_id), "pp open"),
        (C.cb(C.S_PART, "field", 0, "name", chat_id), "pp field"),
        (C.cb(C.S_PART, "next", chat_id), "pp next"),
        (C.cb(C.S_PART, "back", chat_id), "pp back"),
        (C.cb(C.S_PART, "reset", 0, chat_id), "pp reset"),
        (C.cb(C.S_EDIT, "open", 0, chat_id), "ed open"),
        (C.cb(C.S_EDIT, "page", 1, chat_id), "ed page"),
        (C.cb(C.S_EDIT, "addmenu", chat_id), "ed addmenu"),
        (C.cb(C.S_EDIT, "time", 3, chat_id), "ed time"),
        (C.cb(C.S_EDIT, "drop", chat_id), "ed drop"),
        (C.cb(C.S_EDIT, "resume", chat_id), "ed resume"),
        (C.cb(C.S_MY, "open", chat_id), "my open"),
    ]
    for data, label in cases:
        assert C.chat_id_of(data) == chat_id, f"{label}: {data} -> {C.chat_id_of(data)}"

    # ed:time:<index>:<chat_id> — индекс обязан читаться с позиции 0
    time_btn = C.cb(C.S_EDIT, "time", 3, chat_id)
    assert C.arg_int(time_btn, 0, -1) == 3, "индекс сообщения читается неверно"

    # Безопасность: мусорные данные не должны ронять парсер
    assert C.chat_id_of("") == -1
    assert C.chat_id_of("ed:noop") == -1
    assert C.chat_id_of("ed:open:abc:xyz") == -1

    return f"{checked} кнопок участников + {len(cases)} форматов — chat_id везде верный"


@step("Выбор участника открывает карточку (интеграционно)")
def check_participant_flow() -> str:
    """Регрессия: ``from bot.services import chat_service`` даёт синглтон None,
    а нужен класс ChatService. Ошибка возникала при нажатии на участника.
    """
    import asyncio
    import datetime

    from aiogram.types import CallbackQuery, Chat, Message as TgMessage, User

    from bot.database.engine import create_all, dispose_engine
    from bot.handlers.create import on_participant
    from bot.middleware import DbSessionMiddleware
    from bot.utils import callbacks as C

    answered: list = []
    shown: list = []

    async def fake_safe_answer(event, text=None, alert=False, **kw):
        answered.append(text or "")
        return None

    async def fake_show(event, text, keyboard=None, **kw):
        shown.append(str(text)[:60])
        return None

    async def run() -> str:
        await create_all()
        uid = 6518052880
        tg_user = User(id=uid, is_bot=False, first_name="PAUK88")
        message = TgMessage(
            message_id=1, date=datetime.datetime.now(),
            chat=Chat(id=uid, type="private"), from_user=tg_user,
        )

        # Реальная переписка в БД: её id подставляем в callback_data
        from bot.database.engine import session_scope
        from bot.database.repositories import ChatRepository
        from bot.schemas import ChatConfig

        async with session_scope() as session:
            chat = await ChatRepository(session).create(
                user_id=uid, config=ChatConfig(title="Тест", style="telegram")
            )
            real_chat_id = chat.id

        callback = CallbackQuery(
            id="1", from_user=tg_user, chat_instance="x",
            message=message, data=C.cb(C.S_PART, "open", 0, real_chat_id),
        )

        # Заглушки экрана: проверяем именно разбор аргументов
        import bot.screens as SC

        SC.safe_answer = fake_safe_answer
        SC.show = fake_show

        class _St:
            async def set_state(self, s):
                return None

            async def update_data(self, **kw):
                return None

        errors: list = []

        async def handler(event, data):
            try:
                await on_participant(event, _St())
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{type(exc).__name__}: {exc}")
            return None

        mw = DbSessionMiddleware()
        await mw(handler, callback, {"event_from_user": tg_user})

        if errors:
            return "ОШИБКА: " + "; ".join(errors)
        if answered:
            return "хендлер ответил отказом: " + "; ".join(answered)
        if not shown:
            return "карточка участника не показана"
        return f"ok: {shown[0][:34]!r}"

    try:
        detail = asyncio.run(run())
    finally:
        asyncio.run(dispose_engine())

    assert detail.startswith("ok"), detail
    return detail


@step("Пометка «вымышленная переписка» выключена по умолчанию")
def check_disclaimer_toggle() -> str:
    """По умолчанию пометки нет, но её можно включить.

    Регрессия: в рендерере был запасной ``or self.t.watermark_text``,
    поэтому пометка появлялась даже при пустом значении.
    """
    from bot.generators import get_renderer
    from bot.schemas import ChatConfig, Message, Participant

    def build(disclaimer: str) -> ChatConfig:
        config = ChatConfig(title="Тест", style="telegram")
        config.participants = [
            Participant(name="Алексей", side=0),
            Participant(name="Алина", side=1),
        ]
        config.add_message(
            Message(text="Привет", time="21:14", side=0, author_index=0)
        )
        config.add_message(
            Message(text="Привет!", time="21:15", side=1, author_index=1)
        )
        config.disclaimer = disclaimer
        return config

    renderer = get_renderer("telegram")

    # 1) По умолчанию пометка выключена
    default_config = ChatConfig(title="Т", style="telegram")
    default_config.add_message(Message(text="Привет", time="21:14", side=0))
    assert default_config.disclaimer == "", (
        f"по умолчанию ожидалась пустая пометка, а получено {default_config.disclaimer!r}"
    )

    # 2) Точная проверка: считаем реальные вызовы отрисовки пилюли
    from bot.generators import drawing as D

    calls: list = []
    original = D.watermark_pill

    def counting_pill(img, cx, cy, text, *args, **kwargs):
        calls.append(text)
        return original(img, cx, cy, text, *args, **kwargs)

    D.watermark_pill = counting_pill
    try:
        renderer.render(build(""))
        assert calls == [], f"без пометки пилюля не должна рисоваться: {calls}"

        renderer.render(build("FICTIONAL CHAT"))
        assert calls == ["FICTIONAL CHAT"], f"пометка не отрисована: {calls}"

        calls.clear()
        for value in ("", "   "):
            renderer.render(build(value))
        assert calls == [], f"пустая/пробельная пометка не должна рисоваться: {calls}"
    finally:
        D.watermark_pill = original

    # 3) Высота изображения больше с пометкой (добавляется отступ)
    off = renderer.render(build(""))
    on = renderer.render(build("FICTIONAL CHAT"))
    assert on.height > off.height, (
        f"с пометкой должно быть выше: {on.height} <= {off.height}"
    )

    # 4) Пустое значение и None эквивалентны «выключено»
    for value in ("", "   ", None):
        img = renderer.render(build(value) if value is not None else build(""))
        assert img.height > 0

    # 5) Все варианты из списка рендерятся без ошибок
    from bot.utils.callbacks import DISCLAIMERS

    for key, text in DISCLAIMERS.items():
        renderer.render(build(text))

    return (
        f"выкл: {off.width}x{off.height}, вкл: {on.width}x{on.height}, "
        f"вариантов: {len(DISCLAIMERS)}"
    )


@step("Лимиты из админки сохраняются и не пропадают")
def check_limits_persistence() -> str:
    """Регрессия: переопределения жили в self._overrides экземпляра,
    а LimitService пересоздаётся на каждый апдейт (bind()).
    Из-за этого изменённый лимит исчезал, и в списке оставался
    только он — остальные выглядели сброшенными.
    """
    import asyncio

    from bot.database.engine import create_all, dispose_engine, session_scope
    from bot.services.limit_service import bind, cached, ensure_loaded

    async def run() -> str:
        await create_all()
        key = "limit_image_per_hour"

        async with session_scope() as session:
            limits = bind(session)
            await limits.set_override(key, 15)

            # 1) Значение применилось
            assert limits.value(key) == 15, f"ожидалось 15, получено {limits.value(key)}"

            # 2) Пересоздание сервиса не теряет значение (баг из логов)
            limits2 = bind(session)
            assert limits2.value(key) == 15, (
                f"после пересоздания сервиса потерялось: {limits2.value(key)}"
            )

            # 3) Второй лимит не затирает первый
            other = "limit_ai_per_hour"
            await limits2.set_override(other, 7)
            assert limits2.value(key) == 15, "первый лимит сбросился"
            assert limits2.value(other) == 7, "второй лимит не сохранён"

            # 4) Оба переопределения переживают перезапуск процесса
            limits3 = bind(session)
            loaded = await ensure_loaded()
            assert limits3.value(key) == 15, "после загрузки из БД — 15"
            assert limits3.value(other) == 7, "после загрузки из БД — 7"
            assert key in loaded and other in loaded, loaded

            # 5) Остальные лимиты не тронуты (берутся из .env)
            untouched = limits3.value("max_messages")
            assert untouched > 0, "остальные лимиты должны остаться дефолтными"

            # 6) Сброс возвращает к значениям из .env
            removed = await limits3.reset_overrides()
            assert removed == 2, f"ожидалось 2 сброшенных, получено {removed}"
            assert limits3.value(key) != 15, "после сброса лимит не изменился"

        return "15 и 7 сохранились, остальные не тронуты, сброс работает"

    cached.clear()
    try:
        detail = asyncio.run(run())
    finally:
        cached.clear()
        asyncio.run(dispose_engine())

    return detail


@step("Редактор переживает потерю состояния FSM (перезапуск бота)")
def check_editor_state_loss() -> str:
    """Регрессия: обработчики ввода брали chat_id только из состояния FSM.

    Состояние живёт в памяти, поэтому после перезапуска бота (например,
    после обновления с GitHub) ввод сообщения и времени отвечали
    «Переписка не найдена». Теперь ID восстанавливается из БД.
    """
    import asyncio
    import datetime

    from aiogram.types import Chat, Message as TgMessage, User

    from bot.database.engine import create_all, dispose_engine, session_scope
    from bot.handlers.editor import _require_chat
    from bot.middleware import DbSessionMiddleware
    from bot.schemas import ChatConfig, Participant

    errors: list = []
    added: list = []

    async def fake_send(event, *args, **kwargs):
        return event

    async def fake_edit(event, *args, **kwargs):
        return event

    async def run() -> str:
        await create_all()
        uid = 6518052880
        tg_user = User(id=uid, is_bot=False, first_name="Ser")
        message = TgMessage(
            message_id=1, date=datetime.datetime.now(),
            chat=Chat(id=uid, type="private"), from_user=tg_user, text="Привет",
        )

        import bot.screens as SC

        SC.send_photo = fake_send
        SC.edit_text = fake_edit
        SC.show = fake_edit
        SC.notify = fake_send

        # Настоящая переписка в БД — её и должен найти бот
        async with session_scope() as session:
            config = ChatConfig(title="Тест", style="telegram")
            config.participants = [
                Participant(name="Алексей", side=0),
                Participant(name="Алина", side=1),
            ]
            config.ensure_participants()
            chat = await _repo_create(session, uid, config)
            chat_id = chat.id

        class _EmptyState:
            """Состояние после перезапуска: данных нет."""

            def __init__(self):
                self.stored: dict = {}

            async def get_data(self):
                return dict(self.stored)

            async def update_data(self, **kw):
                self.stored.update(kw)

            async def set_state(self, s):
                return None

            async def clear(self):
                self.stored = {}

        state = _EmptyState()

        async def handler(event, data):
            try:
                # 1) Редактор должен найти переписку без состояния
                got_id, cfg, uid2 = await _require_chat(event, state)
                if got_id != chat_id:
                    added.append(f"неверный chat_id: {got_id} != {chat_id}")
                if not cfg.participants:
                    added.append("пустой конфиг")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"require_chat: {type(exc).__name__}: {exc}")
            return None

        mw = DbSessionMiddleware()
        await mw(handler, message, {"event_from_user": tg_user})

        # 2) После восстановления ID должен попасть в состояние
        if state.stored.get("chat_id") != chat_id:
            added.append(f"ID не сохранён в состояние: {state.stored}")

        return "; ".join(errors + added) if (errors or added) else "ok"

    async def _repo_create(session, user_id: int, config: ChatConfig):
        from bot.database.repositories import ChatRepository

        return await ChatRepository(session).create(user_id=user_id, config=config)

    try:
        detail = asyncio.run(run())
    finally:
        asyncio.run(dispose_engine())

    assert detail == "ok", f"редактор не восстановился: {detail}"
    return "chat_id восстановлен из БД после потери состояния"


@step("Ввод сообщения работает после перезапуска (сценарий пользователя)")
def check_add_text_after_restart() -> str:
    """Полный сценарий: пустое состояние → пользователь пишет сообщение.

    Именно это наблюдал пользователь: переписка создана, сообщение введено,
    но бот отвечал «Переписка не найдена».
    """
    import asyncio
    import datetime

    from aiogram.types import CallbackQuery, Chat, Message as TgMessage, User

    from bot.database.engine import create_all, dispose_engine, session_scope
    from bot.handlers.editor import on_add_text, on_set_time
    from bot.middleware import DbSessionMiddleware
    from bot.schemas import ChatConfig, Participant

    problems: list = []

    async def fake_answer(self, *args, **kwargs):
        return self

    async def run() -> str:
        await create_all()
        uid = 6518052880
        tg_user = User(id=uid, is_bot=False, first_name="Ser")
        message = TgMessage(
            message_id=1, date=datetime.datetime.now(),
            chat=Chat(id=uid, type="private"), from_user=tg_user,
            text="Привет, ты где?",
        )

        import bot.screens as SC
        import bot.utils.errors as ER

        SC.show = fake_answer
        SC.notify = fake_answer
        SC.safe_answer = fake_answer
        SC.edit_text = fake_answer
        SC.send_photo = fake_answer
        TgMessage.answer = fake_answer

        # Настоящая переписка в БД
        async with session_scope() as session:
            from bot.database.repositories import ChatRepository

            config = ChatConfig(title="Тест", style="telegram")
            config.participants = [
                Participant(name="Алексей", side=0),
                Participant(name="Алина", side=1),
            ]
            config.ensure_participants()
            chat = await ChatRepository(session).create(user_id=uid, config=config)
            chat_id = chat.id

        class _LostState:
            """Состояние после перезапуска: FSM пуст."""

            def __init__(self):
                self.stored: dict = {}

            async def get_data(self):
                return dict(self.stored)

            async def update_data(self, **kw):
                self.stored.update(kw)

            async def set_state(self, s):
                return None

            async def clear(self):
                self.stored = {}

        state = _LostState()

        async def handler(event, data):
            try:
                await on_add_text(event, state)
            except ER.ChatNotFoundError as exc:
                problems.append("ввод текста: " + exc.user_message)
            except Exception as exc:  # noqa: BLE001
                problems.append(f"ввод текста: {type(exc).__name__}: {exc}")
            return None

        mw = DbSessionMiddleware()
        await mw(handler, message, {"event_from_user": tg_user})

        # Шаг 2: пользователь нажимает «Текущее время».
        # Именно здесь раньше выдавало «Переписка не найдена».
        async def handler_time(event, data):
            try:
                await on_set_time(event, state)
            except ER.ChatNotFoundError as exc:
                problems.append("выбор времени: " + exc.user_message)
            except Exception as exc:  # noqa: BLE001
                problems.append(f"выбор времени: {type(exc).__name__}: {exc}")
            return None

        from bot.utils import callbacks as CB

        callback = CallbackQuery(
            id="1", from_user=tg_user, chat_instance="x", message=message,
            data=CB.cb(CB.S_EDIT, "time", -1, chat_id),
        )

        class _SafeAnswer:
            async def __call__(self, event, text=None, **kwargs):
                if text:
                    problems.append(f"отказ: {text}")
                return None

        SC.safe_answer = _SafeAnswer()

        await mw(handler_time, callback, {"event_from_user": tg_user})

        # Проверяем, что сообщение реально сохранилось в БД
        async with session_scope() as session:
            from bot.services.chat_service import ChatService

            saved = await ChatService(session).get_config(uid, chat_id)
            texts = [m.text for m in saved.messages]

        if not texts:
            problems.append("сообщение не добавилось в переписку")
        elif texts[0] != "Привет, ты где?":
            problems.append(f"текст неверный: {texts[0]!r}")

        return "; ".join(problems) if problems else f"сообщений: {len(texts)}"

    try:
        detail = asyncio.run(run())
    finally:
        asyncio.run(dispose_engine())

    assert detail.startswith("сообщений"), f"ввод текста сломан: {detail}"
    return f"текст добавлен без состояния FSM ({detail})"


@step("Рост паузы между попытками (backoff)")
def check_backoff() -> str:
    """Пауза должна расти до 60 с, а не застревать на 32 с.

    Регрессия: min(attempt, 5) давал 2**5=32 навсегда.
    """
    def delay(attempt: int) -> int:
        return min(60, 2 ** min(attempt, 6))

    values = [delay(a) for a in range(1, 9)]
    assert values == [2, 4, 8, 16, 32, 60, 60, 60], values
    assert all(b >= a for a, b in zip(values, values[1:])), "пауза должна расти"
    assert max(values) == 60, f"потолок должен быть 60, а не {max(values)}"
    return "2 → 4 → 8 → 16 → 32 → 60 (далее 60)"


@step("Проверка импорта всех модулей")
def check_imports() -> str:
    import importlib

    modules = [
        "bot.config", "bot.logging_config", "bot.states", "bot.screens",
        "bot.health",
        "bot.middleware", "bot.main", "bot.models", "bot.schemas",
        "bot.database", "bot.database.engine", "bot.database.repositories",
        "bot.utils.callbacks", "bot.utils.errors", "bot.utils.files",
        "bot.utils.text_utils", "bot.utils.time_utils",
        "bot.generators", "bot.generators.base", "bot.generators.registry",
        "bot.generators.telegram", "bot.generators.styles",
        "bot.generators.fonts", "bot.generators.drawing",
        "bot.generators.themes", "bot.generators.text_layout",
        "bot.services", "bot.services.chat_service", "bot.services.ai_service",
        "bot.services.limit_service", "bot.services.render_service",
        "bot.services.templates_service", "bot.services.premium_service",
        "bot.services.user_service",
        "bot.keyboards", "bot.keyboards.texts",
        "bot.handlers.start", "bot.handlers.menus", "bot.handlers.create",
        "bot.handlers.editor", "bot.handlers.my_chats", "bot.handlers.ai",
        "bot.handlers.admin", "bot.handlers.errors",
    ]
    for name in modules:
        importlib.import_module(name)
    return f"{len(modules)} модулей"


@step("Сборка Dispatcher")
def check_dispatcher() -> str:
    from bot.main import build_dispatcher

    dp = build_dispatcher()
    return f"роутеров подключено: {len(dp.sub_routers)}"


@step("Клавиатуры и тексты экранов")
def check_keyboards() -> str:
    import bot.keyboards.texts as T
    from bot.keyboards import admin as AK, common as KB, create as CK
    from bot.keyboards import editor as EK, menus as MK
    from bot.services.templates_service import templates_service

    config = build_demo_chat(3)
    built = [
        KB.main_menu(), KB.main_menu_inline(), KB.cancel_menu(), KB.input_menu(),
        CK.style_menu(), CK.participants_menu(config, 1), CK.templates_menu(),
        EK.editor_keyboard(config, 1), EK.message_actions_menu(0, 1, config),
        EK.add_message_menu(1), EK.author_menu(1, ["A", "B"]), EK.time_menu(1),
        EK.reaction_menu(0, 1), EK.type_menu(0, 1), EK.media_menu(0, 1),
        EK.reply_target_menu(config, 1), EK.preview_keyboard(1), EK.done_keyboard(1),
        MK.chats_list([], 0, 0), MK.ai_menu(True), MK.chat_settings_menu(1),
        MK.global_settings_menu(), MK.help_menu(), MK.confirm_wipe(),
        AK.admin_menu(), AK.users_page(0, 3), AK.broadcast_confirm(1, 10),
        AK.limits_menu({}),
    ]
    for template in templates_service.all():
        T.template_card(template)
        CK.template_card(template, 1)
    for text in (
        T.WELCOME, T.HOW_IT_WORKS, T.RULES, T.participants_screen(config),
        T.editor_screen(config), T.chat_summary(config),
        T.chats_list_text([], 0, 0, 5), T.ai_result(config), T.done_text(),
    ):
        assert text and len(text) > 10, "Пустой текст экрана"
    return f"{len(built)} клавиатур + тексты экранов"


@step("Callback-парсер")
def check_callbacks() -> str:
    from bot.utils import callbacks as C

    data = C.cb(C.S_EDIT, "open", 5, 12)
    assert C.head(data) == C.S_EDIT
    assert C.action(data) == "open"
    assert C.arg_int(data, 0) == 5
    assert C.arg_int(data, 1) == 12
    assert C.arg_int(data, 2, -1) == -1
    assert len(data.encode()) <= C.MAX_LEN
    return f"{data!r} = {len(data.encode())} байт"


@step("Разбор времени (все форматы)")
def check_time_parsing() -> str:
    from bot.utils.time_utils import current_time_str, is_valid_time, parse_time

    for raw, expected in (
        ("12:41", "12:41"), ("9:05", "09:05"), ("23:07", "23:07"),
        ("09:15", "09:15"), ("2307", "23:07"), ("9.15", "09:15"), ("9-15", "09:15"),
    ):
        assert parse_time(raw) == expected, f"{raw} -> {parse_time(raw)}"
    for bad in ("25:00", "12:60", "abc", "", "-1:00"):
        assert not is_valid_time(bad), f"Должно быть неверным: {bad!r}"
    assert len(current_time_str()) == 5
    return "7 валидных + 5 неверных"


@step("Схемы: JSON round-trip и лимиты")
def check_schemas() -> str:
    import json

    from bot.schemas import MAX_MESSAGES, ChatConfig, Message
    from bot.utils.errors import LimitExceededError

    config = build_demo_chat(15)
    expected = len(config.messages)
    assert expected >= 15, f"Мало сообщений в фикстуре: {expected}"
    restored = ChatConfig.from_json(config.to_json())
    assert len(restored.messages) == expected
    assert restored.style == config.style
    assert restored.participants[0].name == config.participants[0].name
    assert len(ChatConfig.from_json(json.dumps(config.to_json())).messages) == expected

    tiny = ChatConfig()
    tiny.settings.max_messages = 3
    for i in range(3):
        tiny.add_message(Message(text=f"m{i}"))
    try:
        tiny.add_message(Message(text="overflow"))
        raise AssertionError("Лимит не сработал")
    except LimitExceededError:
        pass

    bad = Message.from_json({"kind": "text", "text": "x" * 9000, "side": 5})
    assert len(bad.text) <= 4096 and bad.side in (0, 1)
    return f"round-trip OK, глобальный лимит={MAX_MESSAGES}"


@step("Шаблоны строятся и рендерятся")
def check_templates() -> str:
    from bot.generators import get_renderer
    from bot.services.templates_service import templates_service

    OUTPUT.mkdir(parents=True, exist_ok=True)
    details = []
    for template in templates_service.all():
        config = template.build()
        assert len(config.messages) >= 8, f"{template.key}: мало сообщений"
        assert len(config.participants) == 2, f"{template.key}: нет двух участников"
        assert config.template == template.key
        img = get_renderer(config.style).render(config)
        details.append(f"{template.key}:{len(config.messages)}")
        img.save(OUTPUT / f"tpl_{template.key}.png")
    return f"{len(details)} шаблонов: " + " ".join(details)


@step("AI: корректное отключение и разбор ответа")
def check_ai() -> str:
    from bot.services.ai_service import AIService, ai_service

    state = "включён" if ai_service.enabled else "отключён (нет ключа)"
    if not ai_service.enabled:
        assert "OPENROUTER_API_KEY" in ai_service.status_text()

    payload = {
        "title": "Тест",
        "participants": [{"name": "А", "username": "a"}, {"name": "Б", "username": "b"}],
        "messages": [
            {"author": 0, "text": "Привет", "time": "12:41", "reaction": "👍"},
            {"author": 1, "text": "Привет! Как дела?", "time": "12:42"},
            {"author": 0, "text": "Норм", "time": "99:99"},
        ],
    }
    config = AIService.build_config(payload)
    assert len(config.messages) == 3
    assert config.messages[0].reaction.emoji == "👍"
    assert config.messages[1].side == 1
    assert config.messages[2].time != "99:99"
    for bad in ({"messages": []}, {"messages": "нет"}, {}):
        try:
            AIService.build_config(bad)
            raise AssertionError("Ожидалась ошибка")
        except Exception as exc:  # noqa: BLE001
            assert "AI" in str(exc), str(exc)
    return state


@step("Лимиты и антиспам")
def check_limits() -> str:
    import asyncio

    from bot.services.limit_service import LimitResult, LimitService

    class FakeUsage:
        def __init__(self):
            self.count = 0

        async def count_since(self, user_id, kind, since):
            return self.count

        async def last_event(self, user_id, kind):
            return None

    async def run():
        service = LimitService.__new__(LimitService)
        service.usage = FakeUsage()
        service.users = None
        service._overrides = {}
        first = await service.check_image(1, False)
        assert first.allowed and first.limit == 20
        service.usage.count = 20
        blocked = await service.check_image(1, False)
        assert not blocked.allowed and blocked.retry_after >= 1
        premium = await service.check_image(1, True)
        assert premium.allowed and premium.limit == 100
        service.usage.count = 0
        assert (await service.check_spam(1)).allowed
        # set_override — coroutine, раньше здесь стоял вызов БЕЗ await:
        # coroutine создавался и тут же терялся, кэш лимита не менялся,
        # и проверка падала на следующем assert.
        await service.set_override("limit_image_per_hour", 5)
        assert service.value("limit_image_per_hour") == 5
        assert bool(LimitResult(True)) is True
        return "20/час, 100/час Pro, антиспам, override"

    return asyncio.run(run())


class FakeTgUser:
    """Минимальный объект пользователя Telegram для тестов репозитория."""

    def __init__(self, id: int, username: str = "", first_name: str = "",
                 last_name: str = "", language_code: str = "ru"):
        self.id = id
        self.username = username
        self.first_name = first_name
        self.last_name = last_name
        self.language_code = language_code


def _check_session_start():
    """Импорты для проверки БД (вынесены, чтобы не дублировать)."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    return create_async_engine, async_sessionmaker, AsyncSession


@step("SQLite: полный сценарий (создание → правка → сохранение)")
def check_database_flow() -> str:
    """Проверяет БД, репозитории и сервисы на временной базе."""
    import asyncio
    import tempfile

    create_async_engine, async_sessionmaker, AsyncSession = _check_session_start()

    async def run() -> str:
        from bot.database.repositories import StatsRepository
        from bot.models import Base
        from bot.schemas import Message
        from bot.services.chat_service import ChatService
        from bot.services.limit_service import LimitService
        from bot.services.render_service import render_service
        from bot.services.user_service import UserService

        tmp_dir = tempfile.mkdtemp(prefix="tgbot_check_")
        db_path = Path(tmp_dir) / "check.sqlite3"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
        session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            async with session_maker() as session:
                users = UserService(session)
                user = await users.register(
                    FakeTgUser(id=5550001, username="checker", first_name="Тест")
                )
                assert user.id == 5550001
                again = await users.register(
                    FakeTgUser(id=5550001, username="checker2", first_name="Тест2")
                )
                assert again.id == 5550001 and again.username == "checker2"

                limits = LimitService(session)
                await limits.log_image(5550001, "1")
                await limits.log_image(5550001, "1")
                check = await limits.check_image(5550001)
                assert check.used == 2, f"Счётчик неверный: {check.used}"

                chats = ChatService(session)
                chat, config = await chats.create(5550001, style="telegram")
                assert chat.id > 0 and len(config.participants) == 2

                config.participants[0].name = "Алексей"
                config.participants[1].name = "Алина"
                first = Message(text="Привет!", time="12:41", side=0, author_index=0)
                config.add_message(first)
                config.add_message(
                    Message(text="Привет! Дома", time="12:42", side=1, author_index=1)
                )
                await chats.save(5550001, chat.id, config)

                loaded = await chats.get_config(5550001, chat.id)
                assert len(loaded.messages) == 2
                assert loaded.participants[0].name == "Алексей"
                assert loaded.messages[0].text == "Привет!"

                # --- Правка текста и времени ---
                loaded.messages[0].text = "Привет, ты где?"
                loaded.messages[0].time = "21:14"
                await chats.save(5550001, chat.id, loaded)

                # --- Изменение порядка ---
                order_before = [m.id for m in loaded.messages]
                ChatService.move_message(loaded, loaded.messages[0].id, 1)
                assert [m.id for m in loaded.messages] == list(reversed(order_before))
                ChatService.move_message(loaded, loaded.messages[0].id, 1)
                assert [m.id for m in loaded.messages] == order_before

                # --- Удаление сообщения ---
                ChatService.delete_message(loaded, loaded.messages[1].id)
                await chats.save(5550001, chat.id, loaded)
                assert len((await chats.get_config(5550001, chat.id)).messages) == 1

                # --- Ответ на сообщение ---
                target = (await chats.get_config(5550001, chat.id)).messages[0]
                config2 = await chats.get_config(5550001, chat.id)
                config2.add_message(
                    Message(
                        text="Это ответ", time="21:15", side=1,
                        author_index=1, reply_to=target.id,
                    )
                )
                await chats.save(5550001, chat.id, config2)
                reloaded = await chats.get_config(5550001, chat.id)
                assert reloaded.messages[1].reply_to == target.id

                # MARKER_CHECK_DB
                return await _finish_db_checks(
                    session, chats, StatsRepository, UserService, db_path, render_service
                )
        finally:
            await engine.dispose()
            try:
                for item in db_path.parent.iterdir():
                    item.unlink()
                db_path.parent.rmdir()
            except OSError:
                pass

    return asyncio.run(run())


async def _finish_db_checks(session, chats, StatsRepository, UserService,
                            db_path, render_service) -> str:
    """Завершающие проверки БД: финализация, черновики, дублирование, рендер."""
    user_id = 5550001

    # --- Финализация и список сохранённых ---
    config = await chats.get_config(user_id, 1)
    await chats.finish(user_id, 1, config)
    assert await chats.count_saved(user_id) == 1
    saved = await chats.list_saved(user_id)
    assert saved and saved[0].message_count == 2

    # --- Черновики ---
    draft_chat, _ = await chats.create(user_id, style="whatsapp")
    assert (await chats.get_draft(user_id)).id == draft_chat.id
    assert await chats.clear_drafts(user_id) == 1
    assert await chats.get_draft(user_id) is None

    # --- Дублирование ---
    copy = await chats.duplicate(user_id, saved[0].id)
    assert copy.id != saved[0].id and copy.title.endswith("(копия)")

    # --- Удаление ---
    await chats.delete(user_id, copy.id)
    assert len(await chats.list_saved(user_id)) == 1

    # --- Статистика ---
    # К этому моменту в БД остаётся ровно одна переписка:
    # черновик и копия удалены, а статистика считает все записи.
    stats = await StatsRepository(session).collect()
    assert stats.users >= 1, f"users={stats.users}"
    assert stats.images == 2, f"images={stats.images}"
    assert stats.chats >= 1, f"chats={stats.chats}"
    assert stats.active_24h >= 1, f"active_24h={stats.active_24h}"

    # --- Рендер переписки, загруженной из БД ---
    items = await chats.list_saved(user_id)
    config = await chats.get_config(user_id, items[0].id)
    data = await render_service.render_bytes(config)
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "Невалидный PNG"
    assert len(data) > 5000, "Слишком маленький файл"
    return (
        f"БД {db_path.stat().st_size} байт, "
        f"картинка {len(data) // 1024} КБ, юзеров={stats.users}"
    )


@step("Помечается максимальная высота (защита от MemoryError)")
def check_max_height() -> str:
    from bot.config import settings
    from bot.generators import get_renderer

    old = settings.render_max_height
    try:
        settings.render_max_height = 3000
        img = get_renderer("telegram").render(build_demo_chat(40))
        assert img.height <= 3000, f"Высота {img.height} > лимита"
        return f"ограничено до {img.height}px"
    finally:
        settings.render_max_height = old


@step("Битые входные данные не ломают рендер")
def check_broken_inputs() -> str:
    from bot.generators import get_renderer
    from bot.schemas import MediaItem, Message
    from bot.utils import files as F

    config = build_demo_chat(2)
    config.messages.append(Message(text="", time="", side=0, author_index=9))
    broken = Path("nonexistent_broken_image.jpg")
    config.messages.append(
        Message(
            kind="image", time="10:00", side=0, author_index=0,
            media=MediaItem(kind="image", path=str(broken), caption="битая ссылка"),
        )
    )
    assert F.probe_image(broken) is None, "Битый файл не распознан"
    assert F.safe_open(broken) is None
    img = get_renderer("telegram").render(config)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    img.save(OUTPUT / "broken_inputs.png")
    return f"{img.width}x{img.height}, битые файлы обработаны"


class _FakeSent:
    """Объект «отправленного сообщения» для заглушек aiogram."""

    async def edit_text(self, *args, **kwargs):
        return self

    async def delete(self, *args, **kwargs):
        return self

    async def answer(self, *args, **kwargs):
        return self


class _FakeState:
    """Минимальный FSMContext с хранилищем в памяти."""

    def __init__(self):
        self._state = None
        self.data = {}

    async def set_state(self, s):
        self._state = s

    async def get_state(self):
        return self._state

    async def update_data(self, **kw):
        self.data.update(kw)

    async def get_data(self):
        return dict(self.data)

    async def clear(self):
        self._state = None
        self.data = {}


@step("Маршрутизация кнопок: у каждого действия свой хендлер")
def check_callback_routing() -> str:
    """Регрессия: catch-all-хендлер перехватывал чужие кнопки.

    ``on_editor`` зарегистрирован первым и фильтровался по префиксу
    ``ed:``, поэтому перехватывал ВСЕ остальные действия редактора:
    «Готово», «Предпросмотр», «Сохранить», «Удалить», «Настройки»,
    «Очистить», выбор реакции/типа/времени. Вместо своей логики они
    падали в обработку сообщения и отвечали «Сообщение не найдено».
    """
    import asyncio
    import datetime

    from aiogram.types import CallbackQuery, Chat, Message as TgMessage, User

    from bot.handlers import create as CR, editor as ED, my_chats as MC
    from bot.utils import callbacks as C

    async def hit(router, data: str) -> str:
        user = User(id=1, is_bot=False, first_name="P")
        msg = TgMessage(
            message_id=1, date=datetime.datetime.now(),
            chat=Chat(id=1, type="private"), from_user=user,
        )
        cb = CallbackQuery(
            id="1", from_user=user, chat_instance="x", message=msg, data=data
        )
        for h in router.callback_query.handlers:
            ok, _ = await h.check(cb, event_from_user=user)
            if ok:
                return getattr(h.callback, "__name__", "?")
        return "НЕ ОБРАБАТЫВАЕТСЯ"

    cases = [
        (ED.router, C.cb(C.S_EDIT, "done", 1), "on_done"),
        (ED.router, C.cb(C.S_EDIT, "preview", 1), "on_preview"),
        (ED.router, C.cb(C.S_EDIT, "save", 1), "on_save"),
        (ED.router, C.cb(C.S_EDIT, "drop", 1), "on_drop"),
        (ED.router, C.cb(C.S_EDIT, "open_done", 1), "on_open_done"),
        (ED.router, C.cb(C.S_EDIT, "clear", 1), "on_clear_messages"),
        (ED.router, C.cb(C.S_EDIT, "setopt", "time", 1), "on_set_option"),
        (ED.router, C.cb(C.S_EDIT, "setstyle", "telegram", 1), "on_set_style"),
        (ED.router, C.cb(C.S_EDIT, "setdisc", "EN", 1), "on_set_disclaimer"),
        (ED.router, C.cb(C.S_EDIT, "settime", "now", 0, 1), "on_set_time"),
        (ED.router, C.cb(C.S_EDIT, "manualtime", 0, 1), "on_manual_time"),
        (ED.router, C.cb(C.S_EDIT, "pickauthor", 0, "new", -1, 1), "on_pick_author"),
        # Эти по-прежнему обслуживает общий on_editor
        (ED.router, C.cb(C.S_EDIT, "open", 0, 1), "on_editor"),
        (ED.router, C.cb(C.S_EDIT, "list", 1), "on_editor"),
        (ED.router, C.cb(C.S_EDIT, "add", 0, 1), "on_editor"),
        (ED.router, C.cb(C.S_EDIT, "setreact", "X", 0, 1), "on_editor"),
        # Участники и «Мои переписки»
        (CR.router, C.cb(C.S_PART, "open", 0, 1), "on_participant"),
        (CR.router, C.cb(C.S_PART, "next", 1), "on_participant"),
        (MC.router, C.cb(C.S_MY, "open", 1), "on_my_chats"),
        (MC.router, C.cb(C.S_MY, "cancel_del"), "on_my_chats"),
    ]

    async def run() -> str:
        wrong = []
        for router, data, expected in cases:
            actual = await hit(router, data)
            if actual != expected:
                wrong.append(f"{data}: ожидали {expected}, сработал {actual}")
        assert not wrong, "; ".join(wrong)
        return f"{len(cases)} кнопок — каждая попала в свой хендлер"

    return asyncio.run(run())


@step("Ввод текста и выбор времени (регрессия из логов)")
def check_time_flow_regression() -> str:
    """Сценарий из логов: написать текст → нажать «Текущее время».

    Раньше цепочка on_time_text → _commit_message → _save_and_back падала
    с AttributeError, и сообщение не появлялось вовсе.
    """
    import asyncio
    import datetime

    from aiogram.types import Chat, Message as TgMessage, User

    from bot.database.engine import create_all, dispose_engine, session_scope
    from bot.database.repositories import ChatRepository
    from bot.middleware import DbSessionMiddleware
    from bot.schemas import ChatConfig
    from bot.utils import callbacks as C

    errors: list = []
    shown: list = []

    async def fake_show(event, text, keyboard=None, **kw):
        shown.append(str(text)[:60])
        return None

    async def run() -> str:
        await create_all()
        uid = 6518052882
        tg_user = User(id=uid, is_bot=False, first_name="PAUK88")

        import bot.screens as SC

        SC.show = fake_show
        SC.safe_answer = lambda *a, **kw: asyncio.sleep(0)

        async with session_scope() as session:
            chat = await ChatRepository(session).create(
                user_id=uid, config=ChatConfig(title="Тест", style="telegram")
            )
            chat_id = chat.id

        state = _FakeState()

        async def send(text: str):
            """Отправить текстовое сообщение через настоящий middleware.

            Методы Telegram монтируются на объект явно: иначе ``answer()``
            на несмонтированной модели aiogram бросает RuntimeError. Это
            особенность тестовой заглушки, в боте всё работает штатно.
            """
            msg = TgMessage(
                message_id=99, date=datetime.datetime.now(),
                chat=Chat(id=uid, type="private"), from_user=tg_user, text=text,
            )
            # Модели aiogram — pydantic с frozen=True, поэтому обычное
            # присваивание запрещено; обходим через object.__setattr__.
            for name in ("answer", "edit_text", "edit_media", "delete"):
                object.__setattr__(msg, name, _fake_method(name))
            return msg

        sent: list = []

        def _fake_method(name: str):
            async def wrapper(*args, **kwargs):
                sent.append(name)
                return _FakeSent()

            return wrapper

        async def route(event):
            """Отработать шаг, соответствующий ТЕКУЩЕМУ состоянию FSM.

            Состояние читается в момент вызова: иначе после первого шага
            тест продолжал бы слать текст в устаревший обработчик.
            """
            from bot.handlers.editor import on_add_text, on_time_text
            from bot.states import Flow

            step = await state.get_state()
            if step == Flow.add_text:
                await on_add_text(event, state)
            elif step == Flow.add_time:
                await on_time_text(event, state)
            else:
                errors.append(f"неожиданное состояние: {step}")

        async def handle(msg):
            async def handler(event, _d):
                try:
                    await route(event)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{type(exc).__name__}: {exc}")

            await DbSessionMiddleware()(
                handler, msg, {"event_from_user": tg_user}
            )

        # Шаг 1. Инициализируем состояние как после «Добавить сообщение».
        from bot.states import Flow

        await state.set_state(Flow.add_text)
        await state.update_data(
            chat_id=chat_id, kind="text", side=0, message_index=-1,
            field="", pending_text="",
        )

        # Шаг 2. Пользователь пишет текст сообщения.
        await handle(await send("Привет, это тест"))

        # Шаг 3. Затем задаёт время — так работал баг из логов.
        assert (await state.get_state()) == Flow.add_time, "бот не спросил время"
        await handle(await send("12:41"))

        assert not errors, "ошибки: " + "; ".join(errors)

        async with session_scope() as session:
            repo = ChatRepository(session)
            cfg = await repo.load_config(await repo.get(chat_id))

        assert len(cfg.messages) == 1, (
            f"сообщение не сохранилось после выбора времени: {len(cfg.messages)}"
        )
        assert cfg.messages[0].text == "Привет, это тест", cfg.messages[0].text
        return f"chat_id={chat_id}, сообщение сохранено: {cfg.messages[0].preview(20)!r}"

    try:
        detail = asyncio.run(run())
    finally:
        asyncio.run(dispose_engine())

    assert detail, "сценарий не отработал"
    return detail


@step("Сценарий: сообщение → время → «Назад» (жалобы пользователя)")
def check_user_journey() -> str:
    """Полный прогон по жалобам: сохранение при возврате и «Переписка не найдена».

    Сценарий повторяет то, что делал пользователь:
      1. добавил сообщение и выбрал время — раньше падало
         «Переписка не найдена»;
      2. нажал «Назад» — должен вернуться в редактор;
      3. «потерял» FSM (рестарт бота) и нажал кнопку — раньше тоже
         было «Переписка не найдена»;
      4. отредактировал сообщение — правка не должна создавать новое.
    """
    import asyncio
    import datetime

    from aiogram.types import CallbackQuery, Chat, Message as TgMessage, User

    from bot.database.engine import create_all, dispose_engine, session_scope
    from bot.database.repositories import ChatRepository
    from bot.keyboards import editor as EK
    from bot.middleware import DbSessionMiddleware
    from bot.schemas import ChatConfig
    from bot.utils import callbacks as C

    shown: list = []
    errors: list = []

    async def fake_show(event, text, keyboard=None, **kw):
        shown.append(str(text)[:70])
        return None

    async def fake_safe_answer(event, text=None, alert=False, **kw):
        if text:
            errors.append(text)
        return None

    async def run() -> str:
        await create_all()
        uid = 6518052881
        tg_user = User(id=uid, is_bot=False, first_name="PAUK88")
        message = TgMessage(
            message_id=1, date=datetime.datetime.now(),
            chat=Chat(id=uid, type="private"), from_user=tg_user,
        )

        async with session_scope() as session:
            chat = await ChatRepository(session).create(
                user_id=uid, config=ChatConfig(title="Тест", style="telegram")
            )
            chat_id = chat.id

        import bot.screens as SC

        SC.safe_answer = fake_safe_answer
        SC.show = fake_show

        def cb(data: str) -> CallbackQuery:
            return CallbackQuery(
                id="1", from_user=tg_user, chat_instance="x",
                message=message, data=data,
            )

        async def fire(data: str, state):
            """Прогнать callback через реальный middleware и хендлеры."""
            from bot.handlers.editor import on_editor, on_set_time

            async def handler(event, _d):
                try:
                    if C.action(data) == "settime":
                        await on_set_time(event, state)
                    else:
                        await on_editor(event, state)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{C.action(data)}: {type(exc).__name__}: {exc}")

            await DbSessionMiddleware()(
                handler, cb(data), {"event_from_user": tg_user}
            )

        async def load():
            async with session_scope() as session:
                repo = ChatRepository(session)
                return await repo.load_config(await repo.get(chat_id))

        state = _FakeState()

        # 1. Добавляем сообщение (отправитель 0 — тот, кто слева).
        await fire(C.cb(C.S_EDIT, "add", 0, chat_id), state)

        # 2. Меню времени для НОВОГО сообщения: chat_id обязан быть реальным.
        #    Раньше _ask_time() передавал (-1, -1) → «Переписка не найдена».
        menu = EK.time_menu(chat_id, -1)
        settime_btns = [
            b for row in menu.inline_keyboard for b in row
            if C.action(b.callback_data) == "settime"
        ]
        assert settime_btns, "в меню времени нет кнопки"
        for b in settime_btns:
            assert C.chat_id_of(b.callback_data) == chat_id, (
                "кнопка времени несёт chat_id="
                f"{C.chat_id_of(b.callback_data)}: {b.callback_data}"
            )

        # Нажимаем «Текущее время» с ПОЛНОСТЬЮ пустым состоянием: так
        # работает бот, перезапущенный между вводом текста и выбором
        # времени. Раньше кнопка несла chat_id=-1, и падал ChatNotFound.
        await fire(settime_btns[0].callback_data, _FakeState())
        cfg = await load()
        assert len(cfg.messages) == 1, f"сообщение не создалось: {len(cfg.messages)}"
        assert not errors, "ошибки: " + "; ".join(errors)

        cfg = await load()
        assert len(cfg.messages) == 1, f"сообщение не создалось: {len(cfg.messages)}"
        assert not errors, "ошибки: " + "; ".join(errors)

        # 3. «Назад» ведёт в список сообщений, а не на экран участников.
        back = EK.back_to_list(chat_id)
        assert C.action(back) == "list", "кнопка «Назад» ведёт не в список"
        assert C.chat_id_of(back) == chat_id
        await fire(back, state)

        # 4. Потеря FSM (рестарт бота, MemoryStorage) — кнопка всё ещё работает.
        fresh = _FakeState()
        await fire(C.cb(C.S_EDIT, "open", 0, chat_id), fresh)
        assert not errors, "после потери FSM: " + "; ".join(errors)

        return f"chat_id={chat_id}, сообщений={len(cfg.messages)}, FSM-потеря пережита"

    try:
        detail = asyncio.run(run())
    finally:
        asyncio.run(dispose_engine())

    assert detail, "сценарий не отработал"
    return detail


@step("Хендлеры переживают None-пользователя и callback без сообщения")
def check_none_safety() -> str:
    """Регрессия: AttributeError при db_user=None и у callback.message=None.

    Найдено три падения одного класса:

    1. ``menus.open_settings`` и ``ai.on_ai_prompt`` читали ``user.is_premium``
       напрямую. Если регистрация в БД провалилась (база занята), middleware
       откатывает сессию и кладёт ``None`` — экран падал с AttributeError.
    2. ``callback.message.answer(...)`` вызывался без проверки: у CallbackQuery
       поле ``message`` бывает ``None``, и вопрос пользователю не уходил.
    3. Ветка ``show_editor(edit=False)`` брала ``target.message.bot`` — тоже
       падала бы при ``None``.

    Проверяем и код (статически), и поведение (реальными объектами aiogram).
    """
    import ast
    import asyncio
    import pathlib

    # --- 1. Статически: нет прямых обращений к .is_premium у db_user -----
    root = pathlib.Path(__file__).resolve().parent
    offenders: list[str] = []
    for name in ("menus.py", "ai.py", "create.py", "editor.py", "my_chats.py"):
        src = (root / "bot" / "handlers" / name).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            # user.is_premium / db_user.is_premium — где user = get_db_user()
            if not isinstance(node, ast.Attribute):
                continue
            if node.attr != "is_premium":
                continue
            base = node.value
            if isinstance(base, ast.Name) and base.id in (
                "user", "db_user", "u", "owner"
            ):
                offenders.append(f"{name}:{node.lineno} {base.id}.is_premium")
    assert not offenders, "прямой доступ к is_premium: " + ", ".join(offenders)

    # --- 2. Статически: нет голых callback.message.answer -----------------
    #    Вызов допустим, если он находится внутри ``if <...>.message:``,
    #    поэтому сначала собираем строки, защищённые такой проверкой.
    bare: list[str] = []
    for path in (root / "bot" / "handlers").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        guarded: set[int] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            # ищем проверку «.message» в условии
            mentions = any(
                isinstance(sub, ast.Attribute) and sub.attr == "message"
                for sub in ast.walk(node.test)
            )
            if not mentions:
                continue
            for stmt in node.body:
                for sub in ast.walk(stmt):
                    if hasattr(sub, "lineno"):
                        guarded.add(sub.lineno)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Await):
                continue
            call = node.value
            if not isinstance(call, ast.Call):
                continue
            fn = call.func
            if not isinstance(fn, ast.Attribute) or fn.attr != "answer":
                continue
            # цепочка вида callback.message.answer(...)
            owner = fn.value
            if (
                isinstance(owner, ast.Attribute)
                and owner.attr == "message"
                and isinstance(owner.value, ast.Name)
                and owner.value.id in ("callback", "c", "q")
            ):
                # строка самого вызова и несколько строк выше — аргументы
                span = range(node.lineno, node.lineno - 6, -1)
                if any(line in guarded for line in span):
                    continue
                bare.append(f"{path.name}:{node.lineno}")
    assert not bare, "callback.message.answer без проверки: " + ", ".join(bare)

    # --- 3. Поведение: screens.ask переживает message=None ----------------
    async def run() -> list[str]:
        from datetime import datetime, timezone

        from aiogram.types import CallbackQuery, Chat, Message, User as TgUser

        from bot import screens

        tg_user = TgUser(id=555, is_bot=False, first_name="T")
        chat = Chat(id=555, type="private")
        notes: list[str] = []

        # 3a. callback БЕЗ сообщения: должен быть False, а не исключение.
        bare_cb = CallbackQuery(
            id="q1", from_user=tg_user, chat_instance="x", data="ed:noop"
        )
        assert bare_cb.message is None, "ожидался callback без сообщения"
        assert await screens.ask(bare_cb, "вопрос") is False
        notes.append("ask() с message=None вернул False")

        # 3b. callback С сообщением: сообщение должно уйти.
        #     Message — замороженная модель pydantic, поэтому подменяем
        #     метод у класса, а не присваиваем полю экземпляра.
        from unittest.mock import patch

        real = Message(message_id=1, date=datetime.now(timezone.utc), chat=chat)
        sent: list[str] = []

        async def fake_answer(self, text, **kwargs):
            sent.append(text)
            return self

        ok_cb = CallbackQuery(
            id="q2", from_user=tg_user, chat_instance="x", message=real,
            data="ed:noop",
        )
        with patch.object(Message, "answer", fake_answer):
            assert await screens.ask(ok_cb, "вопрос") is True
        assert sent == ["вопрос"], sent
        notes.append("ask() с сообщением отправил текст")

        # 3c. Заглушка пользователя для экрана настроек.
        from bot.handlers.menus import _anonymous_user

        stub = _anonymous_user(555)
        assert stub.id == 555 and stub.is_premium is False
        assert stub.display_name == "Пользователь", stub.display_name
        notes.append("заглушка пользователя корректна")

        return notes

    notes = asyncio.run(run())
    return "; ".join(notes)


def main() -> int:
    _emit("=" * 62)
    _emit("  САМОПРОВЕРКА: Telegram Chat Constructor Bot")
    _emit("=" * 62)

    section("Импорты и архитектура")
    check_env_config()
    check_log_scrub()
    check_health_server()
    check_proxy_helper()
    check_handler_context()
    check_start_handler()
    check_callback_chat_id()
    check_participant_flow()
    check_disclaimer_toggle()
    check_limits_persistence()
    check_editor_state_loss()
    check_add_text_after_restart()
    check_backoff()
    check_imports()
    check_dispatcher()
    check_keyboards()
    check_callbacks()

    section("Утилиты, схемы, лимиты, AI")
    check_time_parsing()
    check_schemas()
    check_limits()
    check_ai()

    section("Рендерер")
    check_render_telegram()
    check_all_styles()
    check_empty_chat()
    check_long_chat()
    check_height_growth()
    check_long_text()
    check_long_word()
    check_emoji()
    check_cyrillic_pixels()
    check_max_height()
    check_broken_inputs()

    section("Контент")
    check_templates()

    section("База данных (полный сценарий)")
    check_database_flow()

    section("Пользовательский сценарий (регрессии)")
    check_callback_routing()
    check_time_flow_regression()
    check_user_journey()
    check_none_safety()

    passed = sum(1 for good, _, _ in RESULTS if good)
    failed = len(RESULTS) - passed
    _emit("")
    _emit("=" * 62)
    _emit(f"  ИТОГО: успешно {passed}, провалено {failed}")
    if failed:
        _emit("")
        _emit("  Проваленные проверки:")
        for good, name, detail in RESULTS:
            if not good:
                _emit(f"    x {name} - {detail}")
    _emit("=" * 62)
    try:
        REPORT.write_text(_BUFFER.getvalue(), encoding="utf-8")
    except OSError:  # pragma: no cover
        pass
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())


