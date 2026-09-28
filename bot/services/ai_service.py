"""Генерация сценария переписки через OpenRouter.

Если ключ не задан — сервис корректно отключается, остальные
функции бота продолжают работать.

Важно: сгенерированный сценарий — это вымышленный контент.
AI никогда не позиционирует его как реальную переписку.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

import httpx

from bot.config import settings
from bot.schemas import ChatConfig, Message, MessageKind, Participant, Reaction
from bot.utils import text_utils as T
from bot.utils.errors import AIError, AIUnavailableError
from bot.utils.time_utils import current_time_str, is_valid_time

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Ты помощник, который пишет ВЫМЫШЛЕННЫЕ диалоги для юмора, мемов и "
    "контента. Ты никогда не создаёшь тексты, которые можно выдать за реальную "
    "переписку, банковское уведомление, документ или доказательство. "
    "Соблюдай правила: без персональных данных реальных людей, без номеров "
    "карт, без кодов подтверждения и реквизитов."
)

USER_PROMPT = """Придумай вымышленную переписку на русском языке по описанию:

{prompt}

Верни ТОЛЬКО JSON без пояснений в формате:
{{
  "title": "название переписки",
  "participants": [
    {{"name": "Имя 1", "username": "user1"}},
    {{"name": "Имя 2", "username": "user2"}}
  ],
  "messages": [
    {{"author": 0, "text": "текст", "time": "21:14", "reaction": "👍"}},
    {{"author": 1, "text": "ответ", "time": "21:15"}}
  ]
}}

Правила:
- author: 0 — первый участник (слева), 1 — второй (справа);
- от 8 до 24 сообщений, диалог должен читаться как живой;
- время в формате ЧЧ:ММ, нарастает по ходу диалога;
- reaction (если есть) — один эмодзи;
- не более 200 символов в одном сообщении;
- не используй настоящие имена известных людей.
"""

JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


class AIService:
    """Клиент OpenRouter. Умеет корректно отключаться."""

    def __init__(self) -> None:
        self.api_key = settings.openrouter_api_key.strip()
        self.model = settings.openrouter_model.strip() or "openai/gpt-4o-mini"
        self.url = settings.openrouter_base_url

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def status_text(self) -> str:
        if self.enabled:
            return f"AI включён (модель {self.model})"
        return "AI выключен: не задан OPENROUTER_API_KEY"

    async def generate(self, prompt: str, timeout: float = 45.0) -> ChatConfig:
        """Сгенерировать сценарий и вернуть готовый ChatConfig."""
        if not self.enabled:
            raise AIUnavailableError(
                "AI-сценарии недоступны: не задан OPENROUTER_API_KEY. "
                "Остальные функции работают."
            )
        if not prompt or not prompt.strip():
            raise AIError("Опишите сценарий подробнее.")

        logger.info("AI-запрос: модель=%s, длина промпта=%s", self.model, len(prompt))
        raw = await self._request(T.clamp(prompt, 1500), timeout)
        config = self._parse(raw)
        logger.info(
            "AI-сценарий готов: сообщений=%s, участников=%s",
            len(config.messages), len(config.participants),
        )
        return config

    async def _request(self, prompt: str, timeout: float) -> str:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    self.url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://telegram.org",
                        "X-Title": "Telegram Chat Constructor",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": USER_PROMPT.format(prompt=prompt)},
                        ],
                        "temperature": 0.9,
                        "max_tokens": 2000,
                    },
                )
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            logger.warning("AI: таймаут запроса")
            raise AIError("AI не ответил вовремя. Попробуйте ещё раз.") from exc
        except httpx.HTTPStatusError as exc:
            logger.warning("AI: HTTP %s", exc.response.status_code)
            raise AIError(
                f"AI вернул ошибку {exc.response.status_code}. Проверьте ключ и лимиты."
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning("AI: сетевая ошибка: %s", type(exc).__name__)
            raise AIError("Нет связи с AI-сервисом. Попробуйте позже.") from exc
        except ValueError as exc:
            logger.warning("AI: некорректный JSON-ответ")
            raise AIError("AI вернул неожиданный ответ.") from exc

        try:
            return str(data["choices"][0]["message"]["content"] or "")
        except (KeyError, IndexError, TypeError) as exc:
            raise AIError("AI вернул неожиданный ответ.") from exc

    # --- Разбор ответа модели --------------------------------------
    def _parse(self, raw: str) -> ChatConfig:
        payload = self._find_json(raw)
        try:
            data = json.loads(payload)
        except (ValueError, TypeError) as exc:
            logger.warning("AI: JSON не распознан")
            raise AIError("AI вернул нечитаемый сценарий. Попробуйте ещё раз.") from exc
        if not isinstance(data, dict):
            raise AIError("AI вернул неожиданный формат сценария.")
        return self.build_config(data)

    @staticmethod
    def _find_json(raw: str) -> str:
        text = (raw or "").strip()
        if not text:
            raise AIError("AI вернул пустой ответ.")
        if text.startswith("{"):
            return text
        match = JSON_BLOCK_RE.search(text)
        if match:
            return match.group(0)
        raise AIError("AI не вернул структурированный сценарий.")

    @staticmethod
    def build_config(data: Dict[str, Any]) -> ChatConfig:
        """Преобразовать JSON ответа в ChatConfig (с безопасными значениями)."""
        config = ChatConfig(title=T.clamp(str(data.get("title") or "Сценарий"), 60))

        raw_parts = data.get("participants")
        if not isinstance(raw_parts, list) or len(raw_parts) < 2:
            raw_parts = [{"name": "Участник 1"}, {"name": "Участник 2"}]
        config.participants = [
            Participant(
                name=T.clamp(
                    str(p.get("name") or f"Участник {i + 1}"), T.MAX_NAME_LENGTH
                ),
                username=T.ensure_username(str(p.get("username") or "")),
                side=i % 2,
                status="в сети",
            )
            for i, p in enumerate(raw_parts[:2])
            if isinstance(p, dict)
        ]
        config.ensure_participants()

        raw_messages = data.get("messages")
        if not isinstance(raw_messages, list):
            raise AIError("AI не вернул список сообщений.")

        cursor = current_time_str()
        count = 0
        for item in raw_messages:
            if not isinstance(item, dict) or count >= 60:
                continue
            text = T.clamp(str(item.get("text") or ""), 400)
            if not text:
                continue
            author = str(item.get("author", count % 2))
            side = 1 if author in ("1", "True", "true") else 0
            raw_time = str(item.get("time") or cursor)
            time_value = raw_time if is_valid_time(raw_time) else cursor
            emoji = str(item.get("reaction") or "").strip()
            reaction = Reaction(emoji=T.clamp(emoji, 4), count=1) if emoji else None
            config.messages.append(
                Message(
                    kind=MessageKind.TEXT,
                    text=text,
                    time=time_value,
                    side=side,
                    author_index=side,
                    reaction=reaction,
                    read=side == 0 or count % 3 != 0,
                )
            )
            cursor = time_value
            count += 1

        if not config.messages:
            raise AIError("AI не придумал ни одного сообщения.")
        config.template = "ai"
        return config


ai_service = AIService()

__all__ = ["AIService", "ai_service", "SYSTEM_PROMPT", "USER_PROMPT"]