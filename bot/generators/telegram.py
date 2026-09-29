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
        """Фоновые «каракули» в духе обоев Telegram.

        Раньше здесь рисовались ТОЛЬКО эллипсы, из-за чего фон выглядел
        как ровный «горошек», а не как рисунок. Теперь это контурные
        фигуры: сердечко, цветок, молния и звезда.

        Стиль Telegram рисует узор именно здесь, а НЕ в BaseRenderer:
        пока функция жила только в базовом классе, на картинке оставался
        «горошек», потому что подкласс её перекрывал.
        """
        draw = ImageDraw.Draw(img, "RGBA")
        # Узор — едва заметная текстура: слабый контраст и низкая альфа.
        color = mix(self.t.bg_top, self.t.pattern_color, 0.62) + (44,)
        # Шаг и размер подобраны так, чтобы фигуры читались как рисунок.
        # При мелком size (<15px) все пять фигур сливались в кружки.
        step = int(self.width / 4.2)
        size = max(18, step // 7)
        lw = max(2, size // 12)
        row = 0
        y = step // 2
        while y < img.height:
            x = (row % 2) * (step // 2) + step // 2
            while x < img.width:
                kind = (row * 3 + int(x / step)) % 5
                if kind == 0:      # сердечко
                    self._doodle_heart(draw, x, y, size, color, lw)
                elif kind == 1:    # «дружок» — два кружка рядом
                    r = int(size * 0.62)
                    draw.ellipse(
                        [x - size, y - r, x - size + 2 * r, y + r],
                        outline=color, width=lw,
                    )
                    draw.ellipse(
                        [x - r // 2, y - r // 2, x + 3 * r // 2, y + 3 * r // 2],
                        outline=color, width=lw,
                    )
                elif kind == 2:    # листочек
                    draw.ellipse(
                        [x - size, y - size // 2, x + size, y + size // 2],
                        outline=color, width=lw,
                    )
                elif kind == 3:    # «молния»
                    draw.line(
                        [
                            (x + size // 4, y - size),
                            (x - size // 4, y),
                            (x + size // 10, y),
                            (x - size // 5, y + size),
                        ],
                        fill=color, width=lw, joint="curve",
                    )
                else:              # «звезда»-контур
                    pts = []
                    for k in range(10):
                        rr = size if k % 2 == 0 else size * 0.46
                        a = math.pi * k / 5 - math.pi / 2
                        pts.append((x + math.cos(a) * rr, y + math.sin(a) * rr))
                    draw.line(pts + [pts[0]], fill=color, width=lw, joint="curve")
                x += step
            y += step
            row += 1

    @staticmethod
    def _doodle_heart(draw, cx: int, cy: int, size: int, color, lw: int) -> None:
        """Сердечко-контур из двух дуг и двух наклонных линий."""
        r = size // 2
        draw.arc(
            [cx - size, cy - r, cx, cy + r], start=270, end=360, fill=color, width=lw
        )
        draw.arc(
            [cx, cy - r, cx + size, cy + r], start=180, end=270, fill=color, width=lw
        )
        tip = (cx, cy + int(size * 0.9))
        draw.line([(cx - size, cy), tip], fill=color, width=lw)
        draw.line([(cx + size, cy), tip], fill=color, width=lw)


class DarkTelegramRenderer(TelegramRenderer):
    """Тёмная тема Telegram."""

    style_key = "telegram_dark"

    def __init__(self, theme: Optional[Theme] = None, fonts=None, width: Optional[int] = None):
        super().__init__(theme or TELEGRAM_DARK, fonts=fonts, width=width)


__all__ = ["TelegramRenderer", "DarkTelegramRenderer"]
