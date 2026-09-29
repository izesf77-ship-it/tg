"""Графические примитивы для рендерера.

Функции не зависят от конкретной темы, кроме передаваемых цветов.
"""

from __future__ import annotations

import math
from typing import Iterable, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter

RGB = Tuple[int, int, int]
RGBA = Tuple[int, int, int, int]

AVATAR_PALETTE: Sequence[RGB] = (
    (94, 137, 226), (222, 125, 108), (108, 186, 152), (196, 132, 214),
    (238, 168, 92), (108, 158, 226), (222, 132, 176), (128, 190, 200),
    (186, 160, 226), (140, 186, 128), (226, 148, 130), (110, 176, 224),
)


def mix(color_a: RGB, color_b: RGB, ratio: float) -> RGB:
    """Смешать два цвета: ratio=0 -> a, ratio=1 -> b."""
    ratio = min(1.0, max(0.0, ratio))
    return (
        int(color_a[0] + (color_b[0] - color_a[0]) * ratio),
        int(color_a[1] + (color_b[1] - color_a[1]) * ratio),
        int(color_a[2] + (color_b[2] - color_a[2]) * ratio),
    )


def vertical_gradient(size: Tuple[int, int], top: RGB, bottom: RGB) -> Image.Image:
    """Вертикальный градиент заданного размера."""
    width, height = max(1, size[0]), max(1, size[1])
    strip = Image.new("RGB", (1, height))
    px = strip.load()
    for y in range(height):
        px[0, y] = mix(top, bottom, y / max(1, height - 1))
    return strip.resize((width, height), Image.Resampling.BILINEAR)


def rounded_mask(
    size: Tuple[int, int], radius: int, corners: Optional[Iterable[int]] = None
) -> Image.Image:
    """Маска со скруглёнными углами (0 — без скругления)."""
    width, height = max(1, size[0]), max(1, size[1])
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    active = set(corners if corners is not None else (0, 1, 2, 3))
    if len(active) == 4:
        draw.rounded_rectangle([0, 0, width - 1, height - 1], radius=radius, fill=255)
        return mask
    radius = max(0, min(radius, min(width, height) // 2))
    draw.rectangle([0, 0, width - 1, height - 1], fill=255)
    if radius <= 0:
        return mask
    for corner in (0, 1, 2, 3):
        if corner in active:
            continue
        cx = radius if corner in (0, 1) else width - 1 - radius
        cy = radius if corner in (0, 2) else height - 1 - radius
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=0)
    return mask


def paste_rounded(
    canvas: Image.Image,
    image: Image.Image,
    box: Tuple[int, int, int, int],
    radius: int = 24,
    corners: Optional[Iterable[int]] = None,
) -> None:
    """Вставить изображение в canvas со скруглением."""
    x, y, w, h = box
    if w <= 0 or h <= 0:
        return
    resized = image.resize((max(1, w), max(1, h)), Image.Resampling.LANCZOS)
    if resized.mode != "RGBA":
        resized = resized.convert("RGBA")
    resized.putalpha(rounded_mask((max(1, w), max(1, h)), radius, corners))
    canvas.paste(resized, (x, y), resized)


def drop_shadow(
    canvas: Image.Image,
    box: Tuple[int, int, int, int],
    radius: int,
    color: RGBA,
    offset: int = 3,
    blur: int = 8,
) -> None:
    """Мягкая тень под элементом (рисуется в отдельном слое)."""
    x, y, w, h = box
    if w <= 0 or h <= 0:
        return
    pad = blur * 2 + offset + 6
    layer = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.rounded_rectangle(
        [pad, pad, pad + w - 1, pad + h - 1], radius=radius, fill=color
    )
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(layer, (x - pad + offset // 2, y - pad + offset // 2))


def bubble_with_tail(
    canvas: Image.Image,
    box: Tuple[int, int, int, int],
    color: RGB,
    radius: int,
    side: int,
    tail: int,
) -> None:
    """Пузырь сообщения с «хвостиком» снизу (как в мессенджерах).

    Хвостик рисуется в том же слое, что и пузырь, поэтому не выходит
    за границы и не оставляет артефактов на холсте.
    """
    x, y, w, h = box
    if w <= 0 or h <= 0:
        return
    tail_h = max(0, min(int(tail), 14, h // 2))
    pad = tail_h + 8
    layer = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    fill = color + (255,)
    draw.rounded_rectangle([pad, pad, pad + w - 1, pad + h - 1], radius=radius, fill=fill)

    if tail_h > 0:
        # Хвостик: маленький треугольник, примыкающий к нижнему углу
        tip = pad + h + tail_h
        if side == 1:  # справа
            draw.polygon(
                [
                    (pad + w - tail_h - 1, pad + h - 1),
                    (pad + w - 1, pad + h - 1),
                    (pad + w - 1, tip),
                ],
                fill=fill,
            )
        else:  # слева
            draw.polygon(
                [
                    (pad + 1, pad + h - 1),
                    (pad + tail_h + 1, pad + h - 1),
                    (pad + 1, tip),
                ],
                fill=fill,
            )
    canvas.alpha_composite(layer, (x - pad, y - pad))


def circle_avatar(
    canvas: Image.Image,
    center: Tuple[int, int],
    radius: int,
    image: Optional[Image.Image],
    letter: str,
    fm=None,
    letter_size: Optional[int] = None,
    font_color: RGB = (255, 255, 255),
) -> None:
    """Круглый аватар: фото либо цветной круг с первой буквой имени."""
    cx, cy = center
    size = radius * 2
    if image is not None:
        try:
            face = image.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
            mask = Image.new("L", (size, size), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
            face.putalpha(mask)
            canvas.alpha_composite(face, (cx - radius, cy - radius))
            return
        except (OSError, ValueError):  # pragma: no cover - битое фото
            pass
    color = (
        AVATAR_PALETTE[sum(ord(c) for c in letter) % len(AVATAR_PALETTE)]
        if letter else AVATAR_PALETTE[0]
    )
    ImageDraw.Draw(canvas).ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius], fill=color + (255,)
    )
    if fm is not None and letter:
        fm.draw_text(
            ImageDraw.Draw(canvas), (cx, cy), letter.upper()[:1],
            letter_size or int(radius * 1.05), font_color + (255,), anchor="mm",
        )


def draw_checks(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    size: int,
    color: RGB,
    double: bool = False,
) -> None:
    """Галочки прочтения (одна или две)."""
    stroke = max(2, size // 9)
    unit = size

    def check(offset_x: int) -> None:
        draw.line(
            [
                (offset_x + unit * 0.06, y + unit * 0.52),
                (offset_x + unit * 0.34, y + unit * 0.80),
                (offset_x + unit * 0.92, y + unit * 0.16),
            ],
            fill=color + (255,), width=stroke, joint="curve",
        )

    check(0)
    if double:
        check(int(unit * 0.62))


def waveform(
    draw: ImageDraw.ImageDraw,
    box: Tuple[int, int, int, int],
    color: RGB,
    seed: int = 0,
    bars: int = 26,
) -> None:
    """Звуковая дорожка голосового (детерминированная по seed).

    Раньше полоски были узкими (45% шага) и короткими, из-за чего ряд
    читался как «гороши», а не как волна. Теперь полоски плотнее,
    а высоты ограничены снизу, чтобы дорожка не выглядела пунктиром.
    """
    x, y, w, h = box
    if w <= 0 or h <= 0:
        return
    step = max(3, int(w / bars))
    bar_w = max(3, int(step * 0.62))
    # Дорожка занимает всю ширину: отступы слева/справа не нужны.
    for i in range(bars):
        phase = math.sin((i + 1) * 0.62 + seed * 1.7) * 0.5 + 0.5
        noise = ((i * 37 + seed * 13) % 11) / 11.0
        # Разброс высот усилен, иначе полоски выглядят одинаковыми
        # «пупырышками», а не звуковой волной.
        ratio = 0.18 + 0.82 * (0.72 * phase + 0.28 * noise) ** 1.25
        bar_h = max(int(h * 0.26), int(h * min(1.0, ratio)))
        bx = x + i * step
        by = y + (h - bar_h) // 2
        draw.rounded_rectangle(
            [bx, by, bx + bar_w, by + bar_h], radius=bar_w // 2, fill=color + (255,)
        )


def play_button(
    draw: ImageDraw.ImageDraw, center: Tuple[int, int], radius: int, bg: RGB, fg: RGB
) -> None:
    """Кнопка воспроизведения — круг с оптически центрированным треугольником.

    Раньше вершины задавались от ``cx`` напрямую, из-за чего треугольник
    уезжал вправо: его визуальный центр (OPTICAL center) левее
    геометрического. Теперь треугольник строится по центру и сдвигается
    на долю радиуса влево, как в настоящем плеере.
    """
    cx, cy = center
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=bg + (255,))

    # Равносторонний треугольник со стороной 1.0*radius.
    side = radius * 1.05
    hgt = side * math.sqrt(3) / 2
    left = cx - side / 2
    tri = [
        (left, cy - hgt / 2),
        (left, cy + hgt / 2),
        (left + side, cy),
    ]
    # Компенсация оптического смещения треугольника.
    shift = radius * 0.13
    tri = [(px + shift, py) for px, py in tri]
    draw.polygon(tri, fill=fg + (255,))


def file_icon(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], color: RGB) -> None:
    """Иконка файла: скруглённый квадрат с белым документом и сгибом.

    Раньше рисовался просто синий прямоугольник, а «сгиб» — полупрозрачным
    треугольником поверх него. Из-за этого угол выглядел срезанным, и
    иконка читалась как обрывок бумаги. Теперь это синяя подложка с
    белым листом внутри и настоящим сгибом в углу.
    """
    x, y, w, h = box
    radius = max(3, int(min(w, h) * 0.22))
    # Синяя подложка-скруглённый квадрат.
    draw.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=color + (255,))

    pad = max(2, int(min(w, h) * 0.24))
    dx0, dy0 = x + pad, y + pad
    dx1, dy1 = x + w - pad, y + h - pad
    fold = int(min(dx1 - dx0, dy1 - dy0) * 0.34)

    # Белый лист: верхний правый угол срезан по диагонали.
    sheet = [
        (dx0, dy0),
        (dx1 - fold, dy0),
        (dx1, dy0 + fold),
        (dx1, dy1),
        (dx0, dy1),
    ]
    draw.polygon(sheet, fill=(255, 255, 255, 255))
    # Сгиб: маленький треугольник «отогнутого» угла.
    draw.polygon(
        [(dx1 - fold, dy0), (dx1, dy0 + fold), (dx1 - fold, dy0 + fold)],
        fill=color + (255,),
    )


def photo_placeholder(
    size: Tuple[int, int],
    top: RGB,
    bottom: RGB,
    icon_color: RGB,
    fm=None,
    label: str = "",
    seed: int = 0,
) -> Image.Image:
    """Заглушка «фотография»: градиент, блики, силуэт гор и подпись."""
    width, height = max(8, size[0]), max(8, size[1])
    img = vertical_gradient((width, height), top, bottom).convert("RGBA")
    draw = ImageDraw.Draw(img)

    for i in range(4):
        r = int(min(width, height) * (0.28 + i * 0.16))
        cx = int(width * (0.2 + 0.2 * ((seed + i) % 3)))
        cy = int(height * (0.25 + 0.15 * ((seed + i) % 4)))
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        ImageDraw.Draw(overlay).ellipse(
            [cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, 30)
        )
        img.alpha_composite(overlay)

    # Солнце
    sun_r = max(6, int(min(width, height) * 0.09))
    sun_cx, sun_cy = int(width * 0.76), int(height * 0.24)
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [sun_cx - sun_r, sun_cy - sun_r, sun_cx + sun_r, sun_cy + sun_r],
        fill=(255, 255, 255, 90),
    )
    img.alpha_composite(glow)

    # Горы — светлым силуэтом, а не чёрным
    hill = (255, 255, 255, 70)
    back = (255, 255, 255, 110)
    base_y = int(height * 0.80)
    draw.polygon(
        [
            (int(width * 0.05), base_y),
            (int(width * 0.30), int(height * 0.46)),
            (int(width * 0.55), base_y),
        ],
        fill=hill,
    )
    draw.polygon(
        [
            (int(width * 0.40), base_y),
            (int(width * 0.63), int(height * 0.55)),
            (int(width * 0.95), base_y),
        ],
        fill=back,
    )
    if fm is not None and label:
        fm.draw_text(
            draw, (width // 2, int(height * 0.10)), label,
            max(18, int(height * 0.085)), (255, 255, 255, 235), anchor="ma",
        )
    return img


def sticker_card(size: int, emoji: str, fm, gradient_index: int = 0) -> Image.Image:
    """Квадратная карточка стикера."""
    palette = (
        ((255, 214, 102), (255, 168, 96)),
        ((150, 220, 255), (110, 160, 250)),
        ((190, 255, 190), (110, 210, 160)),
        ((255, 180, 220), (200, 120, 240)),
        ((255, 200, 160), (245, 140, 110)),
    )
    top, bottom = palette[gradient_index % len(palette)]
    img = vertical_gradient((size, size), top, bottom).convert("RGBA")
    if fm is not None and emoji:
        fm.draw_text(
            ImageDraw.Draw(img), (size // 2, int(size * 0.52)), emoji,
            int(size * 0.52), (255, 255, 255, 255), anchor="mm",
        )
    return img


def paper_texture(img: Image.Image, strength: int = 6, seed: int = 0) -> Image.Image:
    """Лёгкий шум поверх фона — имитация текстуры обоев."""
    import random

    rng = random.Random(seed)
    width, height = img.size
    small = (max(1, width // 3), max(1, height // 3))
    noise = Image.new("L", small)
    noise.putdata(
        [rng.randint(128 - strength, 128 + strength) for _ in range(small[0] * small[1])]
    )
    noise = noise.resize((width, height), Image.Resampling.BILINEAR)
    overlay = Image.merge(
        "RGBA", (noise, noise, noise, Image.new("L", (width, height), 26))
    )
    img.alpha_composite(overlay)
    return img


def watermark_pill(
    canvas: Image.Image,
    center_x: int,
    y: int,
    text: str,
    fm,
    size: int,
    fg: RGB,
    bg: RGB,
    alpha: int = 165,
    radius: int = 18,
) -> int:
    """Ненавязчивая пометка «FICTIONAL CHAT». Возвращает высоту блока."""
    if not text:
        return 0
    pad_x, pad_y = int(size * 0.9), int(size * 0.45)
    w = int(fm.measure(text, size)) + pad_x * 2
    h = int(size * 1.95)
    x = max(8, center_x - w // 2)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(
        [0, 0, w - 1, h - 1], radius=min(radius, h // 2), fill=bg + (alpha,)
    )
    canvas.alpha_composite(layer, (x, y))
    fm.draw_text(
        ImageDraw.Draw(canvas), (center_x, y + h // 2), text,
        size, fg + (255,), anchor="mm",
    )
    return h


def legend(canvas: Image.Image, center_x: int, y: int, text: str, fm, size: int, fg: RGB) -> int:
    """Простая подпись подсказки (без подложки)."""
    if not text:
        return 0
    fm.draw_text(
        ImageDraw.Draw(canvas), (center_x, y), text, size, fg + (255,), anchor="ma"
    )
    return int(size * 1.5)


__all__ = [
    "AVATAR_PALETTE", "mix", "vertical_gradient", "rounded_mask", "paste_rounded",
    "drop_shadow", "bubble_with_tail", "circle_avatar", "draw_checks", "waveform",
    "play_button", "file_icon", "photo_placeholder", "sticker_card", "paper_texture",
    "watermark_pill", "legend",
]
