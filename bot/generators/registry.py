"""Реестр стилей: описание для UI и фабрика рендереров."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Type

from bot.config import settings
from bot.generators.base import BaseRenderer
from bot.generators.styles import (
    MessengerRenderer,
    SimpleRenderer,
    WhatsAppRenderer,
)
from bot.generators.telegram import DarkTelegramRenderer, TelegramRenderer
from bot.schemas import ChatConfig

logger = logging.getLogger(__name__)


@dataclass
class StyleDefinition:
    key: str
    title: str
    description: str
    premium_only: bool = False
    renderer: Optional[Type[BaseRenderer]] = None


AVAILABLE_STYLES: List[StyleDefinition] = [
    StyleDefinition(
        key="telegram",
        title="Telegram",
        description="Классический светлый Telegram",
        renderer=TelegramRenderer,
    ),
    StyleDefinition(
        key="telegram_dark",
        title="Dark Telegram",
        description="Тёмная тема Telegram",
        renderer=DarkTelegramRenderer,
    ),
    StyleDefinition(
        key="whatsapp",
        title="WhatsApp",
        description="Зелёные пузыри и светлый фон",
        renderer=WhatsAppRenderer,
    ),
    StyleDefinition(
        key="messenger",
        title="Messenger",
        description="Синие градиентные пузыри",
        premium_only=True,
        renderer=MessengerRenderer,
    ),
    StyleDefinition(
        key="simple",
        title="Простой чат",
        description="Минимализм без лишних деталей",
        renderer=SimpleRenderer,
    ),
]

_BY_KEY: Dict[str, StyleDefinition] = {s.key: s for s in AVAILABLE_STYLES}
_renderers: Dict[str, Type[BaseRenderer]] = {
    s.key: s.renderer for s in AVAILABLE_STYLES if s.renderer
}

DEFAULT_STYLE = "telegram"


def style_definition(key: str) -> StyleDefinition:
    return _BY_KEY.get((key or "").lower(), _BY_KEY[DEFAULT_STYLE])


def style_title(key: str) -> str:
    return style_definition(key).title


def available_styles(premium: bool = False) -> List[StyleDefinition]:
    return [s for s in AVAILABLE_STYLES if premium or not s.premium_only]


def get_renderer(
    style: str, width: Optional[int] = None, fonts=None
) -> BaseRenderer:
    """Создать рендерер для стиля (с кэшем по стилю)."""
    key = (style or DEFAULT_STYLE).lower()
    renderer_cls = _renderers.get(key, TelegramRenderer)
    use_width = width or settings.render_width or 1080
    try:
        return renderer_cls(fonts=fonts, width=use_width)
    except Exception as exc:  # pragma: no cover - защита от битых тем
        logger.error("Не удалось создать рендерер %s: %s", key, exc)
        return TelegramRenderer(fonts=fonts, width=use_width)


def render_chat(
    config: ChatConfig, style: Optional[str] = None, width: Optional[int] = None
):
    """Отрисовать переписку выбранным стилем."""
    renderer = get_renderer(style or config.style, width=width)
    return renderer.render(config)


__all__ = [
    "StyleDefinition",
    "AVAILABLE_STYLES",
    "DEFAULT_STYLE",
    "style_definition",
    "style_title",
    "available_styles",
    "get_renderer",
    "render_chat",
]
