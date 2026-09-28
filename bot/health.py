"""Минимальный HTTP-сервис для healthcheck и прокси хостинга.

Бот общается с Telegram через long polling, но платформа (Traefik)
ожидает, что приложение слушает порт из переменной ``PORT``.
Без этого в логах появляется предупреждение, а домен отдаёт 502.

Сервис намеренно простой: он ничего не делает, кроме ответа 200,
и не должен влиять на работу бота. Отдельный поток, ошибки не фатальны.
"""

from __future__ import annotations

import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logger = logging.getLogger(__name__)

DEFAULT_PORT = 8080

_STATUS = {"bot": "starting", "telegram": "unknown"}


def set_status(bot: str = None, telegram: str = None) -> None:
    """Обновить состояние, отдаваемое в /health."""
    if bot:
        _STATUS["bot"] = bot
    if telegram:
        _STATUS["telegram"] = telegram


class _Handler(BaseHTTPRequestHandler):
    server_version = "ChatConstructor/1.0"

    def _reply(self, code: int, body: str, ctype: str = "text/plain; charset=utf-8") -> None:
        payload = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):  # pragma: no cover
            pass

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path in ("/", "/health", "/healthz"):
            import json

            self._reply(
                200,
                json.dumps({"status": "ok", **_STATUS}, ensure_ascii=False),
                "application/json; charset=utf-8",
            )
        else:
            self._reply(404, "not found")

    def log_message(self, fmt: str, *args) -> None:  # noqa: A002
        # Доступ к healthcheck не должен засорять логи бота
        logger.debug("health: " + fmt, *args)


def start_health_server(port: int | None = None) -> ThreadingHTTPServer | None:
    """Запустить HTTP-сервис в фоновом потоке.

    Любая ошибка (порт занят, прав нет) не должна мешать работе бота —
    поэтому вместо исключения возвращается ``None``.
    """
    if port is None:
        raw = os.environ.get("PORT") or os.environ.get("HEALTH_PORT")
        try:
            port = int(raw) if raw else DEFAULT_PORT
        except ValueError:
            port = DEFAULT_PORT

    if os.environ.get("DISABLE_HEALTH_SERVER", "").strip().lower() in ("1", "true", "yes"):
        logger.info("HTTP-сервис отключён (DISABLE_HEALTH_SERVER)")
        return None

    try:
        server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    except OSError as exc:
        logger.warning("Не удалось поднять HTTP-сервис на порту %s: %s", port, exc)
        return None

    thread = threading.Thread(target=server.serve_forever, name="health", daemon=True)
    thread.start()
    logger.info("HTTP-сервис слушает 0.0.0.0:%s (healthcheck)", port)
    return server


__all__ = ["start_health_server", "set_status", "DEFAULT_PORT"]
