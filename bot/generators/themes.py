"""Цветовые темы и метрики интерфейса для разных стилей переписки."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

RGB = Tuple[int, int, int]
RGBA = Tuple[int, int, int, int]


@dataclass
class Theme:
    """Цвета и размеры элементов интерфейса."""

    key: str
    title: str

    # Фон
    bg_top: RGB
    bg_bottom: RGB
    pattern_color: RGB

    # Шапка
    header_bg: RGB
    header_fg: RGB
    header_sub: RGB
    header_border: RGB
    header_accent: RGB

    # Пузыри
    in_bg: RGB
    out_bg: RGB
    in_text: RGB
    out_text: RGB
    in_shadow: RGBA
    out_shadow: RGBA

    # Метаданные
    in_meta: RGB
    out_meta: RGB
    in_check: RGB
    out_check: RGB
    out_check_read: RGB

    # Реакции
    reaction_bg: RGB
    reaction_fg: RGB
    reaction_self_bg: RGB
    reaction_self_fg: RGB
    reaction_border: RGB

    # Ответы
    quote_bar_in: RGB
    quote_bar_out: RGB
    quote_text_in: RGB
    quote_text_out: RGB
    quote_name_in: RGB
    quote_name_out: RGB

    # Служебные элементы
    service_bg: RGB
    service_fg: RGB
    date_bg: RGB
    date_fg: RGB
    watermark_fg: RGB
    watermark_bg: RGB
    forward_fg_in: RGB
    forward_fg_out: RGB

    # Метрики
    width: int = 1080
    header_height: int = 148
    side_margin: int = 34
    bubble_radius: int = 26
    bubble_tail: int = 20
    avatar_size: int = 78
    bubble_gap: int = 14
    font_message: int = 34
    font_name: int = 33
    font_meta: int = 27
    font_title: int = 38
    font_subtitle: int = 28
    line_spacing: float = 1.32
    pad_x: int = 30
    pad_y: int = 22
    gradient_bubbles: bool = True
    show_read_double: bool = True
    watermark_text: str = "FICTIONAL CHAT"
    watermark_text_ru: str = "ВЫМЫШЛЕННАЯ ПЕРЕПИСКА"

    @property
    def message_line_height(self) -> int:
        return int(self.font_message * self.line_spacing)

    @property
    def meta_line_height(self) -> int:
        return int(self.font_meta * 1.15)


TELEGRAM_LIGHT = Theme(
    key="telegram", title="Telegram",
    bg_top=(237, 240, 245), bg_bottom=(228, 233, 240), pattern_color=(214, 221, 230),
    header_bg=(255, 255, 255), header_fg=(28, 28, 30), header_sub=(122, 130, 140),
    header_border=(228, 230, 234), header_accent=(61, 138, 232),
    in_bg=(255, 255, 255), out_bg=(232, 246, 214),
    in_text=(24, 26, 30), out_text=(24, 26, 30),
    in_shadow=(0, 0, 0, 16), out_shadow=(0, 0, 0, 12),
    in_meta=(140, 148, 158), out_meta=(122, 140, 105),
    in_check=(160, 168, 178), out_check=(140, 158, 122), out_check_read=(61, 138, 232),
    reaction_bg=(245, 246, 248), reaction_fg=(90, 96, 106),
    reaction_self_bg=(224, 238, 255), reaction_self_fg=(45, 110, 190),
    reaction_border=(214, 218, 224),
    quote_bar_in=(90, 160, 235), quote_bar_out=(140, 190, 90),
    quote_text_in=(126, 134, 144), quote_text_out=(112, 132, 96),
    quote_name_in=(61, 138, 232), quote_name_out=(96, 150, 62),
    service_bg=(206, 210, 216), service_fg=(72, 78, 86),
    date_bg=(222, 226, 232), date_fg=(86, 92, 102),
    watermark_fg=(148, 156, 168), watermark_bg=(255, 255, 255),
    forward_fg_in=(112, 150, 210), forward_fg_out=(120, 150, 90),
)

TELEGRAM_DARK = Theme(
    key="telegram_dark", title="Dark Telegram",
    bg_top=(22, 30, 38), bg_bottom=(18, 24, 31), pattern_color=(34, 44, 54),
    header_bg=(28, 36, 45), header_fg=(240, 243, 246), header_sub=(140, 150, 162),
    header_border=(38, 47, 58), header_accent=(108, 168, 240),
    in_bg=(30, 40, 50), out_bg=(44, 82, 120),
    in_text=(236, 240, 244), out_text=(236, 240, 244),
    in_shadow=(0, 0, 0, 46), out_shadow=(0, 0, 0, 40),
    in_meta=(138, 150, 162), out_meta=(160, 186, 208),
    in_check=(130, 146, 160), out_check=(150, 178, 200), out_check_read=(126, 200, 138),
    reaction_bg=(38, 50, 62), reaction_fg=(206, 214, 222),
    reaction_self_bg=(52, 92, 138), reaction_self_fg=(224, 240, 255),
    reaction_border=(56, 70, 84),
    quote_bar_in=(108, 168, 240), quote_bar_out=(120, 176, 226),
    quote_text_in=(150, 160, 172), quote_text_out=(176, 200, 220),
    quote_name_in=(130, 186, 246), quote_name_out=(150, 196, 240),
    service_bg=(48, 60, 72), service_fg=(178, 188, 198),
    date_bg=(46, 58, 70), date_fg=(190, 200, 210),
    watermark_fg=(112, 124, 138), watermark_bg=(30, 40, 50),
    forward_fg_in=(126, 178, 240), forward_fg_out=(150, 190, 230),
)

WHATSAPP = Theme(
    key="whatsapp", title="WhatsApp",
    bg_top=(233, 237, 232), bg_bottom=(223, 228, 222), pattern_color=(212, 219, 211),
    header_bg=(7, 94, 84), header_fg=(255, 255, 255), header_sub=(203, 226, 222),
    header_border=(6, 84, 75), header_accent=(126, 214, 196),
    in_bg=(255, 255, 255), out_bg=(220, 248, 198),
    in_text=(17, 27, 33), out_text=(17, 27, 33),
    in_shadow=(0, 0, 0, 14), out_shadow=(0, 0, 0, 12),
    in_meta=(140, 150, 158), out_meta=(103, 121, 108),
    in_check=(150, 158, 166), out_check=(140, 156, 144), out_check_read=(53, 189, 235),
    reaction_bg=(240, 242, 244), reaction_fg=(86, 96, 106),
    reaction_self_bg=(214, 234, 250), reaction_self_fg=(30, 110, 190),
    reaction_border=(205, 210, 216),
    quote_bar_in=(24, 164, 152), quote_bar_out=(24, 164, 152),
    quote_text_in=(120, 130, 140), quote_text_out=(100, 122, 106),
    quote_name_in=(7, 94, 84), quote_name_out=(7, 94, 84),
    service_bg=(210, 216, 210), service_fg=(70, 80, 86),
    date_bg=(17, 27, 33), date_fg=(255, 255, 255),
    watermark_fg=(150, 160, 150), watermark_bg=(255, 255, 255),
    forward_fg_in=(24, 150, 140), forward_fg_out=(24, 140, 100),
)

MESSENGER = Theme(
    key="messenger", title="Messenger",
    bg_top=(245, 246, 250), bg_bottom=(236, 238, 244), pattern_color=(228, 231, 238),
    header_bg=(24, 119, 242), header_fg=(255, 255, 255), header_sub=(214, 230, 252),
    header_border=(20, 104, 224), header_accent=(255, 255, 255),
    in_bg=(233, 235, 240), out_bg=(0, 132, 255),
    in_text=(24, 26, 32), out_text=(255, 255, 255),
    in_shadow=(0, 0, 0, 12), out_shadow=(0, 0, 0, 20),
    in_meta=(124, 132, 144), out_meta=(222, 236, 255),
    in_check=(160, 166, 176), out_check=(210, 228, 252), out_check_read=(255, 255, 255),
    reaction_bg=(245, 246, 250), reaction_fg=(84, 90, 100),
    reaction_self_bg=(0, 132, 255), reaction_self_fg=(255, 255, 255),
    reaction_border=(214, 218, 226),
    quote_bar_in=(0, 132, 255), quote_bar_out=(255, 255, 255),
    quote_text_in=(112, 120, 132), quote_text_out=(224, 238, 255),
    quote_name_in=(0, 110, 230), quote_name_out=(255, 255, 255),
    service_bg=(214, 218, 226), service_fg=(70, 78, 90),
    date_bg=(206, 212, 222), date_fg=(70, 78, 90),
    watermark_fg=(150, 156, 168), watermark_bg=(255, 255, 255),
    forward_fg_in=(0, 130, 240), forward_fg_out=(230, 242, 255),
)

SIMPLE = Theme(
    key="simple", title="Простой чат",
    bg_top=(250, 250, 251), bg_bottom=(240, 241, 244), pattern_color=(236, 238, 242),
    header_bg=(255, 255, 255), header_fg=(30, 32, 38), header_sub=(130, 138, 150),
    header_border=(230, 232, 236), header_accent=(90, 120, 160),
    in_bg=(255, 255, 255), out_bg=(216, 234, 248),
    in_text=(28, 30, 36), out_text=(28, 30, 36),
    in_shadow=(0, 0, 0, 12), out_shadow=(0, 0, 0, 10),
    in_meta=(146, 152, 162), out_meta=(110, 128, 148),
    in_check=(166, 172, 182), out_check=(140, 160, 180), out_check_read=(90, 140, 190),
    reaction_bg=(244, 246, 250), reaction_fg=(92, 100, 112),
    reaction_self_bg=(214, 232, 250), reaction_self_fg=(48, 106, 176),
    reaction_border=(216, 220, 228),
    quote_bar_in=(150, 170, 195), quote_bar_out=(120, 160, 200),
    quote_text_in=(138, 146, 158), quote_text_out=(104, 132, 162),
    quote_name_in=(90, 120, 160), quote_name_out=(70, 116, 170),
    service_bg=(226, 230, 236), service_fg=(96, 104, 116),
    date_bg=(232, 236, 242), date_fg=(100, 108, 120),
    watermark_fg=(160, 166, 176), watermark_bg=(255, 255, 255),
    forward_fg_in=(120, 145, 175), forward_fg_out=(100, 140, 190),
)

THEMES = {
    "telegram": TELEGRAM_LIGHT,
    "telegram_dark": TELEGRAM_DARK,
    "whatsapp": WHATSAPP,
    "messenger": MESSENGER,
    "simple": SIMPLE,
}

DEFAULT_THEME = TELEGRAM_LIGHT


def get_theme(key: str) -> Theme:
    """Тема по ключу; при неизвестном ключе — Telegram Light."""
    return THEMES.get((key or "").strip().lower(), DEFAULT_THEME)


__all__ = ["Theme", "RGB", "RGBA", "THEMES", "get_theme", "DEFAULT_THEME"]
