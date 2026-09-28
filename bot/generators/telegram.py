"""Рендерер в стиле Telegram — основной и наиболее детальный.

Особенности:
* классические «хвостики» у пузырей;
* скругление углов в стиле Telegram (асимметричное);
* светлая/тёмная темы, фоновый узор;
* аватары у входящих сообщений, Premium-значок;
* галочки прочтения, реакции, ответы, пересылки, медиа.
"""

from __future__ import annotations

from typing import List, Optional

from PIL import Image, ImageDraw

from bot.generators.base import BaseRenderer
from bot.generators.drawing import mix
from bot.generators.themes import TELEGRAM_DARK, TELEGRAM_LIGHT, Theme


class TelegramRenderer(BaseRenderer):
    """Рендерер переписки в стиле Telegram."""

    style_key = "telegram"

    def __init__(self, theme: Optional[Theme] = None, fonts=None, width: Optional[int] = None):
        super().__init__(theme or TELEGRAM_LIGHT, fonts=fonts, width=width)

    def draw_pattern(self, img: Image.Image) -> None:
        """Фоновый узор: редкие «капли», как в обоях Telegram."""
        draw = ImageDraw.Draw(img, "RGBA")
        color = mix(self.t.bg_top, self.t.pattern_color, 0.9)
        step = int(self.width / 7)
        radius = max(4, step // 7)
        row = 0
        y = step // 2
        while y < img.height:
            x = (row % 2) * (step // 2) + step // 3
            while x < img.width:
                draw.ellipse(
                    [x - radius, y - radius, x + radius, y + radius], fill=color + (38,)
                )
                x += step
            y += step
            row += 1


class DarkTelegramRenderer(TelegramRenderer):
    """Тёмная тема Telegram."""

    style_key = "telegram_dark"

    def __init__(self, theme: Optional[Theme] = None, fonts=None, width: Optional[int] = None):
        super().__init__(theme or TELEGRAM_DARK, fonts=fonts, width=width)


__all__ = ["TelegramRenderer", "DarkTelegramRenderer"]
