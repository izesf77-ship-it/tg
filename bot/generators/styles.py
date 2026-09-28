"""Стили WhatsApp, Messenger и «Простой чат» — на общем движке."""

from __future__ import annotations

from typing import Optional

from PIL import Image, ImageDraw

from bot.generators.base import BaseRenderer, Layout
from bot.generators.drawing import mix
from bot.generators.themes import MESSENGER, SIMPLE, WHATSAPP, Theme


class WhatsAppRenderer(BaseRenderer):
    """Стиль WhatsApp: плотные пузыри, «лапки», тёмно-зелёная шапка."""

    style_key = "whatsapp"

    def __init__(self, theme: Optional[Theme] = None, fonts=None, width: Optional[int] = None):
        super().__init__(theme or WHATSAPP, fonts=fonts, width=width)

    def draw_pattern(self, img: Image.Image) -> None:
        """Обои WhatsApp: редкие «каракули»-кружки."""
        draw = ImageDraw.Draw(img, "RGBA")
        color = mix(self.t.bg_top, self.t.pattern_color, 0.95)
        step = int(self.width / 6)
        r = max(3, step // 8)
        for row, y in enumerate(range(step // 2, img.height, step)):
            x = (row % 2) * (step // 2) + step // 4
            while x < img.width:
                draw.ellipse([x - r, y - r, x + r, y + r], fill=color + (60,))
                x += step


class MessengerRenderer(BaseRenderer):
    """Стиль Messenger: синие градиентные пузыри, скругление до «капли»."""

    style_key = "messenger"

    def __init__(self, theme: Optional[Theme] = None, fonts=None, width: Optional[int] = None):
        super().__init__(theme or MESSENGER, fonts=fonts, width=width)

    def draw_pattern(self, img: Image.Image) -> None:
        draw = ImageDraw.Draw(img, "RGBA")
        color = mix(self.t.bg_top, self.t.pattern_color, 0.95)
        step = int(self.width / 8)
        r = max(3, step // 10)
        for row, y in enumerate(range(step, img.height, step)):
            x = (row % 2) * (step // 2)
            while x < img.width:
                draw.ellipse([x - r, y - r, x + r, y + r], fill=color + (30,))
                x += step

    def _paint_header_actions(self, draw, h: int) -> None:
        """У Messenger справа — телефон и видео."""
        draw = super()._paint_header_actions(draw, h)


class SimpleRenderer(BaseRenderer):
    """Минималистичный чат: плоские цвета, без хвостиков и узоров."""

    style_key = "simple"

    def __init__(self, theme: Optional[Theme] = None, fonts=None, width: Optional[int] = None):
        super().__init__(theme or SIMPLE, fonts=fonts, width=width)

    def paint_background(self, height: int, with_pattern=None) -> Image.Image:
        """Плоский фон без узора и градиента."""
        return BaseRenderer.paint_background(self, height, None)


__all__ = ["WhatsAppRenderer", "MessengerRenderer", "SimpleRenderer"]
