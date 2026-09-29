"""Базовый рендерер переписки.

Архитектура — два прохода:
1. **layout** — для каждого сообщения рассчитываются высота, ширина,
   перенос строк и служебные блоки. Высота изображения ещё неизвестна.
2. **paint** — создаётся изображение точной высоты и всё рисуется.

Благодаря этому высота растёт автоматически: 5 или 500 сообщений.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw

from bot.config import settings
from bot.generators import drawing as D
from bot.generators.fonts import FontManager, get_font_manager
from bot.generators.text_layout import fit_single_line, wrap_text
from bot.generators.themes import Theme, get_theme
from bot.schemas import ChatConfig, ChatSettings, Message, MessageKind, Participant
from bot.utils import files as F

logger = logging.getLogger(__name__)

TAIL_CORNERS_IN = (0, 1, 3)   # скругление: без правого-нижнего
TAIL_CORNERS_OUT = (0, 2, 3)  # скругление: без левого-нижнего


@dataclass
class Layout:
    """Результат расчёта одного сообщения."""

    message: Message
    kind: MessageKind
    side: int
    height: int = 0
    width: int = 0
    lines: List[str] = field(default_factory=list)
    quote_name: str = ""
    quote_lines: List[str] = field(default_factory=list)
    media_box: Optional[Tuple[int, int]] = None
    has_bubble: bool = True
    tail: bool = False
    extra: Dict = field(default_factory=dict)


class BaseRenderer:
    """Общий движок отрисовки. Наследники задают тему и нюансы."""

    style_key: str = "telegram"

    def __init__(
        self,
        theme: Optional[Theme] = None,
        fonts: Optional[FontManager] = None,
        width: Optional[int] = None,
    ) -> None:
        self.theme = theme or get_theme(self.style_key)
        if width:
            self.theme.width = int(width)
        self.fm: FontManager = fonts or get_font_manager()
        # Флаги отображения приходят из настроек конкретной переписки
        # и обновляются на каждом render().
        self.settings: ChatSettings = ChatSettings()

    # --- Свойства-Shortcut ------------------------------------------
    @property
    def t(self) -> Theme:
        return self.theme

    @property
    def width(self) -> int:
        return self.theme.width

    @property
    def header_height(self) -> int:
        return self.theme.header_height

    # --- Главный метод ----------------------------------------------
    def render(self, config: ChatConfig) -> Image.Image:
        """Отрисовать переписку и вернуть изображение (RGB)."""
        config.ensure_participants()
        self.settings = config.settings or ChatSettings()
        messages = self._visible_messages(config)
        layouts = [self.layout(m, config, idx) for idx, m in enumerate(messages)]

        body_height = sum(lay.height for lay in layouts) + self._bottom_padding(config)
        total = self.header_height + body_height
        max_h = settings.render_max_height
        if max_h and total > max_h:
            logger.warning("Изображение выше лимита (%s>%s), обрезаем", total, max_h)
            total = max_h

        img = self._create_background(total)
        self._paint_header(img, config)

        draw = ImageDraw.Draw(img, "RGBA")
        y = self.header_height
        for lay in layouts:
            if y + lay.height > total:
                break
            y = self.paint_message(img, draw, lay, config, y)
        self.paint_scroll_button(img)
        self.paint_input_bar(img)
        self._paint_watermark(img, config, total)
        return img.convert("RGB")

    def render_to_bytes(self, config: ChatConfig, fmt: str = "PNG") -> bytes:
        """Отрисовать и вернуть байты изображения."""
        import io

        buffer = io.BytesIO()
        self.render(config).save(buffer, format=fmt, optimize=True)
        return buffer.getvalue()

    # --- Вспомогательное --------------------------------------------
    def _visible_messages(self, config: ChatConfig) -> List[Message]:
        limit = config.settings.max_messages
        messages = list(config.messages)
        if config.settings.date_dividers and not any(
            m.kind == MessageKind.DATE for m in messages
        ):
            messages = self._inject_dividers(messages)
        return messages[-limit:] if limit else messages

    def _inject_dividers(self, messages: List[Message]) -> List[Message]:
        """Разделитель «Сегодня» перед первым сообщением."""
        if not messages:
            return messages
        from bot.schemas import Message as M
        from bot.utils.time_utils import today_label

        divider = M(
            kind=MessageKind.DATE,
            text=today_label(),
            side=0,
            date_label=today_label(),
        )
        return [divider, *messages]

    def _bottom_padding(self, config: ChatConfig) -> int:
        base = int(self.t.font_meta * 4.2)
        if self.t.show_input_bar:
            base += self.t.input_bar_height
        if config.disclaimer:
            base += int(self.t.font_meta * 3.4)
        return base

    def paint_input_bar(self, img: Image.Image) -> None:
        """Нижняя панель ввода: скруглённое поле, скрепка и микрофон.

        На референсе это «плавающая» панель с отступами, а в её правой
        части — круглая синяя кнопка микрофона.
        """
        h = self.t.input_bar_height
        if h <= 0 or img.height < h + self.t.side_margin:
            return
        draw = ImageDraw.Draw(img, "RGBA")
        m = self.t.side_margin
        top = img.height - h + int(m * 0.5)
        box = (m, top, img.width - m, top + h - m)

        D.drop_shadow(img, box, int(h * 0.42), (0, 0, 0, 26), offset=2, blur=12)
        draw.rounded_rectangle(
            list(box), radius=int(h * 0.42), fill=self.t.input_bg + (255,)
        )

        cy = top + (h - m) // 2
        icon = self.t.input_icon + (255,)
        # Скрепка слева
        ix = m + int(h * 0.30)
        r = int(h * 0.15)
        lw = max(3, r // 4)
        draw.line(
            [(ix, cy - r * 0.6), (ix, cy + r * 0.8)],
            fill=icon, width=lw, joint="curve",
        )
        draw.arc(
            [ix - r * 0.9, cy - r * 1.1, ix + r * 0.9, cy + r * 0.5],
            start=270, end=90, fill=icon, width=lw,
        )
        # Плейсхолдер
        text_x = ix + r * 1.6
        self.fm.draw_text(
            draw, (text_x, cy - self.t.font_meta // 2 - 2), "Message",
            self.t.font_meta, self.t.input_fg + (255,),
        )
        # Синяя круглая кнопка микрофона справа
        mr = int(h * 0.26)
        mx = img.width - m - mr - int(h * 0.14)
        draw.ellipse(
            [mx - mr, cy - mr, mx + mr, cy + mr], fill=self.t.mic_bg + (255,)
        )
        self._draw_mic_glyph(draw, mx, cy, int(mr * 0.92))

    @staticmethod
    def _draw_mic_glyph(draw, cx: int, cy: int, size: int) -> None:
        """Белый значок микрофона внутри синей кнопки.

        Раньше здесь рисовались контурный прямоугольник и дуга, и вместе
        они читались как «смайлик». Теперь это настоящий микрофон:
        капсула-головка, «держатель»-дуга под ней и ножка.
        """
        white = (255, 255, 255, 255)
        lw = max(3, size // 7)
        head_w = max(3, int(size * 0.30))
        head_h = max(5, int(size * 0.52))
        head_top = cy - int(size * 0.44)
        # головка — вертикальная капсула
        draw.rounded_rectangle(
            [cx - head_w, head_top, cx + head_w, head_top + head_h * 2],
            radius=head_w, fill=white,
        )
        # держатель — дуга снизу
        draw.arc(
            [cx - int(size * 0.46), cy - int(size * 0.20),
             cx + int(size * 0.46), cy + int(size * 0.36)],
            start=0, end=180, fill=white, width=lw,
        )
        # ножка
        draw.line(
            [(cx, cy + int(size * 0.36)), (cx, cy + int(size * 0.62))],
            fill=white, width=lw,
        )

    def paint_scroll_button(self, img: Image.Image) -> None:
        """Круглая кнопка «вниз» над полем ввода (как на референсе)."""
        if not self.t.show_scroll_button or not self.t.show_input_bar:
            return
        r = int(self.t.input_bar_height * 0.24)
        cy = img.height - self.t.input_bar_height - int(r * 1.5)
        cx = img.width - self.t.side_margin - r - int(self.t.input_bar_height * 0.14)
        D.drop_shadow(
            img, (cx - r, cy - r, r * 2, r * 2), r, (0, 0, 0, 34), 2, 10
        )
        draw = ImageDraw.Draw(img, "RGBA")
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r], fill=self.t.scroll_bg + (255,)
        )
        a = int(r * 0.42)
        lw = max(3, r // 6)
        draw.line(
            [(cx - a, cy - a // 2), (cx, cy + a // 2), (cx + a, cy - a // 2)],
            fill=self.t.scroll_fg + (255,), width=lw, joint="curve",
        )

    def _create_background(self, height: int) -> Image.Image:
        pattern = None
        if self.settings.show_pattern:
            pattern = self.draw_pattern
        img = self.paint_background(height, pattern)
        return img

    def paint_background(self, height: int, with_pattern: Optional[callable] = None) -> Image.Image:
        """Фон: вертикальный градиент + деликатный узор."""
        img = D.vertical_gradient(
            (self.width, max(1, height)), self.t.bg_top, self.t.bg_bottom
        ).convert("RGBA")
        if with_pattern is not None:
            try:
                with_pattern(img)
            except Exception as exc:  # pragma: no cover - узор не критичен
                logger.debug("Узор фона не отрисован: %s", exc)
        return img

    def draw_pattern(self, img: Image.Image) -> None:
        """Фоновый узор в стиле мессенджера.

        Раньше здесь была «сетка точек» из заливных эллипсов — фон
        выглядел как ровный горошек. Теперь рисуются контурные
        «каракули» (сердечко, цветок, молния, звезда), как на референсе.
        """
        draw = ImageDraw.Draw(img, "RGBA")
        color = D.mix(self.t.bg_top, self.t.pattern_color, 0.62) + (44,)
        # При мелком size все фигуры сливались в кружки, поэтому размер
        # увеличен, а шаг сетки сокращён — узор читается как рисунок.
        step = int(self.width / 4.2)
        size = max(18, step // 7)
        lw = max(2, size // 12)
        y = step // 2
        row = 0
        while y < img.height:
            x = (row % 2) * (step // 2) + step // 2
            while x < img.width:
                kind = (row * 3 + int(x / step)) % 4
                if kind == 0:      # сердечко
                    self._doodle_heart(draw, x, y, size, color, lw)
                elif kind == 1:    # цветок: сердцевина и лепестки
                    r = max(3, int(size * 0.30))
                    draw.ellipse(
                        [x - r, y - r, x + r, y + r], outline=color, width=lw
                    )
                    for k in range(5):
                        a = math.pi * 2 * k / 5 - math.pi / 2
                        px = x + math.cos(a) * r * 2.1
                        py = y + math.sin(a) * r * 2.1
                        draw.ellipse(
                            [px - r, py - r, px + r, py + r],
                            outline=color, width=lw,
                        )
                elif kind == 2:    # «молния»
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

    # --- Геометрия пузыря -------------------------------------------
    def avatar_reserved(self, side: int) -> int:
        """Ширина, занятая аватаром слева (только для входящих).

        В стиле Telegram аватаров у сообщений нет (они только в шапке) —
        поэтому резервируется 0.
        """
        if side != 0 or not self.t.avatar_in_messages:
            return 0
        return self.t.avatar_size + self.t.bubble_gap

    def max_bubble_width(self, side: int) -> int:
        ratio = self.settings.bubble_max_ratio
        available = self.width - 2 * self.t.side_margin - self.avatar_reserved(side)
        return int(min(available, self.width * ratio))

    def text_width_for(self, side: int) -> int:
        """Ширина области текста внутри пузыря."""
        return max(60, self.max_bubble_width(side) - 2 * self.t.pad_x)

    def check_size(self) -> int:
        return int(self.t.font_meta * 0.72)

    def checks_width(self, message: Message) -> int:
        """Ширина блока галочек (0, если галочки не рисуются)."""
        if not (self.settings.show_time and self.settings.show_checks):
            return 0
        if message.side != 1:
            return 0
        size = self.check_size()
        return int(size * 1.62) if self.t.show_read_double else int(size * 0.9)

    def time_block(self, message: Message) -> Tuple[int, int]:
        """(ширина блока «время + галочки», размер шрифта времени)."""
        if not self.settings.show_time:
            return 0, 0
        size = self.t.font_meta
        w = int(self.fm.measure(message.time or "", size))
        checks = self.checks_width(message)
        if checks:
            w += checks + int(size * 0.35)
        return w, size

    def _wrap_with_time(
        self, message: Message, text_w: int, lay: Layout
    ) -> List[str]:
        """Перенос текста с резервированием места под время на последней строке."""
        raw = message.text
        if not raw:
            return []
        meta_w = int(lay.extra.get("time_w", 0)) or self.time_block(message)[0]
        lines = wrap_text(raw, self.fm, self.t.font_message, text_w)
        if not lines:
            return []
        if meta_w:
            tail = lines[-1]
            if self.fm.measure(tail, self.t.font_message) + meta_w + 14 > text_w:
                room = max(60, text_w - meta_w - 14)
                lines = lines[:-1] + wrap_text(
                    tail, self.fm, self.t.font_message, room
                )
        return lines

    def _bubble_content_width(self, lay: Layout, max_w: int) -> int:
        """Фактическая ширина пузыря по содержимому (с местом под время)."""
        pad_x = self.t.pad_x
        widest = 0
        for line in lay.lines:
            widest = max(widest, self.fm.measure(line, self.t.font_message))
        if lay.media_box:
            widest = max(widest, lay.media_box[0])
        if lay.quote_lines:
            widest = max(
                widest,
                self.fm.measure(lay.quote_name or "", self.t.font_name)
                + self.t.font_meta * 3.2,
            )

        w = widest + 2 * pad_x
        meta_w = int(lay.extra.get("time_w", 0))
        if lay.lines and meta_w:
            # Последняя строка + служебный блок должны помещаться рядом
            last = self.fm.measure(lay.lines[-1], self.t.font_message)
            w = max(w, last + meta_w + 2 * pad_x + 10)
        if lay.extra.get("reaction_h"):
            w = max(w, self.t.font_meta * 4.4)
        return max(int(self.t.font_message * 3.2), min(max_w, int(w) + 2))

    # --- Раскладка (проход 1) ---------------------------------------
    def layout(self, message: Message, config: ChatConfig, index: int) -> Layout:
        """Рассчитать высоту и содержимое одного сообщения."""
        kind = message.kind
        side = 0 if message.side == 0 else 1

        if kind == MessageKind.DATE:
            return self._layout_date(message)
        if kind == MessageKind.SERVICE:
            return self._layout_service(message)
        if kind == MessageKind.STICKER:
            return self._layout_sticker(message, config)

        lay = Layout(message=message, kind=kind, side=side, tail=self.settings.show_tail)
        max_w = self.max_bubble_width(side)
        text_w = self.text_width_for(side)

        quote_name, quote_lines = self._quote_for(message, config, text_w)
        if quote_lines:
            lay.quote_name = quote_name
            lay.quote_lines = quote_lines

        media_h, media_w = self._media_size(message, max_w)
        if media_h:
            lay.media_box = (media_w, media_h)

        lines = self._wrap_with_time(message, text_w, lay)
        lay.lines = lines

        line_h = self.t.message_line_height
        content_h = line_h * max(1, len(lines)) if lines else 0

        quote_h = 0
        if lay.quote_lines:
            quote_h = int(self.t.font_meta * 2.4) + len(lay.quote_lines) * int(
                self.t.font_meta * 1.32
            ) + int(self.t.pad_y * 0.5)

        forward_h = 0
        if kind == MessageKind.FORWARD and message.forward_from:
            forward_h = int(self.t.font_meta * 1.75)

        pad_y = self.t.pad_y
        time_w, time_size = self.time_block(message)
        height = pad_y * 2 + content_h + quote_h + forward_h
        if media_h:
            height += media_h + int(self.t.pad_y * 0.7)
        if not lines and not media_h:
            height = pad_y * 2 + time_size + int(self.t.pad_y * 0.2)
        if lines and time_w:
            height += int(time_size * 0.55)

        # В Telegram реакция находится ВНУТРИ пузыря, в его нижнем краю.
        # Раньше для неё резервировалось место СНАРУЖИ (высота пузыря
        # уменьшалась на reaction_h, а пилюля рисовалась под ним), из-за
        # чего реакция висела отдельной плашкой под сообщением.
        reaction_h = 0
        if message.reaction and self.settings.show_reactions:
            reaction_h = int(self.t.font_meta * 1.7)

        # Высота пузыря включает место под реакцию внутри.
        lay.height = height + reaction_h
        lay.extra["time_w"] = time_w
        lay.extra["time_size"] = time_size
        lay.extra["reaction_h"] = reaction_h
        lay.extra["body_h"] = height
        lay.width = self._bubble_content_width(lay, max_w)
        return lay

    def _quote_for(
        self, message: Message, config: ChatConfig, text_w: int
    ) -> Tuple[str, List[str]]:
        """Данные блока «ответ на сообщение»."""
        if not message.reply_to:
            return "", []
        target = config.find(message.reply_to)
        if target is None:
            return "", []
        author = self._author_name(config, target)
        body = target.preview(90) or target.type_icon()
        size = int(self.t.font_meta * 1.05)
        width = max(40, int(text_w * 0.86))
        return author, wrap_text(body, self.fm, size, width, max_lines=3)

    def _author_name(self, config: ChatConfig, message: Message) -> str:
        participants = config.participants
        if 0 <= message.author_index < len(participants):
            return participants[message.author_index].short_name
        return "Участник"

    def _media_size(self, message: Message, max_w: int) -> Tuple[int, int]:
        """Размер медиа-блока внутри пузыря (0,0 — если медиа нет)."""
        media = message.media
        if media is None or message.kind not in (
            MessageKind.IMAGE, MessageKind.VOICE, MessageKind.FILE
        ):
            return 0, 0

        inner = max(60, max_w - 2 * self.t.pad_x)
        if message.kind == MessageKind.IMAGE:
            w = inner
            h = int(w * 0.66)
            size = F.probe_image(media.path) if media.path else None
            if size:
                nat_w, nat_h = size
                h = int(w * nat_h / max(1, nat_w))
                limit = int(inner * 0.92)
                if h > limit:
                    h = limit
                    w = int(h * nat_w / max(1, nat_h))
            return max(1, h), max(1, w)
        if message.kind == MessageKind.VOICE:
            return int(self.t.font_message * 2.2), inner
        return int(self.t.font_message * 2.6), inner

    def _layout_date(self, message: Message) -> Layout:
        size = int(self.t.font_meta * 0.98)
        h = int(size * 2.6)
        return Layout(
            message=message, kind=MessageKind.DATE, side=0,
            height=h + int(self.t.font_meta * 1.6), width=0, has_bubble=False,
            extra={"pill_h": h, "font_size": size},
        )

    def _layout_service(self, message: Message) -> Layout:
        size = int(self.t.font_meta * 0.98)
        max_w = int(self.width * 0.86)
        lines = wrap_text(message.text or "", self.fm, size, max_w - int(size * 2.2))
        line_h = int(size * 1.35)
        h = line_h * max(1, len(lines)) + int(size * 1.5)
        return Layout(
            message=message, kind=MessageKind.SERVICE, side=0,
            height=h + int(self.t.font_meta * 1.2), width=0, has_bubble=False,
            lines=lines, extra={"font_size": size, "line_h": line_h},
        )

    def _layout_sticker(self, message: Message, config: ChatConfig) -> Layout:
        max_w = int(self.width * 0.46)
        size = max(120, max_w)
        h = size + int(self.t.font_meta * 0.8)
        if message.text:
            h += int(self.t.font_meta * 1.6) * max(
                1, len(wrap_text(message.text, self.fm, self.t.font_meta, max_w))
            )
        _ = config
        return Layout(
            message=message, kind=MessageKind.STICKER, side=0 if message.side == 0 else 1,
            height=h + int(self.t.font_meta * 1.2), width=size, has_bubble=False,
            extra={"sticker_size": size},
        )

    # --- Отрисовка шапки (проход 2) ---------------------------------
    def _paint_header(self, img: Image.Image, config: ChatConfig) -> None:
        draw = ImageDraw.Draw(img, "RGBA")
        h = self.header_height
        m = self.t.header_margin if self.t.float_header else 0
        if m > 0:
            # Парящая шапка: скруглённая карточка с отступами, как в
            # мобильном Telegram (на референсе она не во всю ширину).
            D.drop_shadow(
                img, (m, m, self.width - 2 * m, h - 2 * m),
                self.t.header_radius, (0, 0, 0, 30), offset=2, blur=10,
            )
            draw.rounded_rectangle(
                [m, m, self.width - 1 - m, h - 1 - m],
                radius=self.t.header_radius, fill=self.t.header_bg + (255,),
            )
        else:
            draw.rectangle([0, 0, self.width - 1, h - 1], fill=self.t.header_bg + (255,))
            draw.line(
                [0, h - 1, self.width - 1, h - 1], fill=self.t.header_border + (255,), width=2
            )

        pad = m if m else 0
        # Кнопка «назад»
        back_x = int(self.width * 0.045) + pad
        cy = h // 2
        stroke = max(3, h // 26)
        draw.line(
            [
                (back_x + stroke * 2, cy - stroke * 2),
                (back_x, cy),
                (back_x + stroke * 2, cy + stroke * 2),
            ],
            fill=self.t.header_sub + (255,), width=stroke, joint="curve",
        )

        # Аватар собеседника
        participants = config.participants
        partner = next((p for p in participants if p.side == 0), None)
        av_r = self.t.avatar_size // 2
        av_cx = back_x + stroke * 4 + av_r
        av_cy = cy
        self._paint_avatar(img, av_cx, av_cy, av_r, partner)

        text_x = av_cx + av_r + int(self.t.bubble_gap * 1.2)
        max_text = self.width - text_x - int(self.width * 0.18)

        # Имя в чате
        if partner is not None:
            title = partner.title
            if self.settings.show_avatars_in_header:
                pass
            title = fit_single_line(title, self.fm, self.t.font_title, max_text)
            self.fm.draw_text(
                draw, (text_x, int(h * 0.30)), title,
                self.t.font_title, self.t.header_fg + (255,),
            )
            if partner.premium:
                self._draw_star(
                    draw,
                    int(text_x + self.fm.measure(title, self.t.font_title)) + 12,
                    int(h * 0.30) + self.t.font_title // 2,
                    int(self.t.font_title * 0.34),
                )
            if self.settings.header_status and partner.status:
                sub = fit_single_line(
                    partner.status_line(), self.fm, self.t.font_subtitle, max_text
                )
                self.fm.draw_text(
                    draw, (text_x, int(h * 0.30) + self.t.font_title + 8), sub,
                    self.t.font_subtitle, self.t.header_sub + (255,),
                )
        else:
            self.fm.draw_text(
                draw, (text_x, int(h * 0.32)), config.title[:48],
                self.t.font_title, self.t.header_fg + (255,),
            )

        self._paint_header_actions(draw, h)

    def _paint_header_actions(self, draw: ImageDraw.ImageDraw, h: int) -> None:
        """Иконки справа в шапке (поиск и меню)."""
        x = self.width - int(self.width * 0.10)
        cy = h // 2
        color = self.t.header_sub + (200,)
        r = int(self.t.font_title * 0.34)
        lw = max(3, r // 7)
        # «лупа»
        draw.ellipse([x - r, cy - r, x + r, cy + r], outline=color, width=lw)
        draw.line([(x + r * 0.7, cy + r * 0.7), (x + r * 1.5, cy + r * 1.5)],
                  fill=color, width=lw)
        # «⋮»
        mx = self.width - int(self.width * 0.045)
        for i in (-1, 0, 1):
            draw.ellipse(
                [mx - lw, cy + i * r - lw, mx + lw, cy + i * r + lw], fill=color
            )

    def _draw_star(self, draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int) -> None:
        """Значок Premium (пятиконечная звезда)."""
        import math as _m

        points = []
        for i in range(10):
            angle = _m.pi / 2 + i * _m.pi / 5
            radius = size if i % 2 == 0 else size * 0.45
            points.append((cx + radius * _m.cos(angle), cy - radius * _m.sin(angle)))
        draw.polygon(points, fill=(92, 168, 240, 255))

    def _paint_avatar(
        self,
        img: Image.Image,
        cx: int,
        cy: int,
        radius: int,
        participant: Optional[Participant],
    ) -> None:
        photo = F.safe_open(participant.avatar_path) if participant and participant.avatar_path else None
        letter = (participant.name[:1] if participant else "?") or "?"
        D.circle_avatar(
            img, (cx, cy), radius, photo, letter, self.fm,
            letter_size=int(radius * 1.05),
            font_color=self.t.header_fg if self.t.key in ("simple",) else (255, 255, 255),
        )
        if participant is not None and participant.premium:
            r = max(10, radius // 3)
            D.drop_shadow(img, (cx + radius - r * 2, cy + radius - r * 2, r * 2, r * 2),
                          r, (0, 0, 0, 60), 0, 4)
            ImageDraw.Draw(img, "RGBA").ellipse(
                [cx + radius - r * 2, cy + radius - r * 2,
                 cx + radius, cy + radius],
                fill=(92, 168, 240, 255),
            )
            self._draw_star(
                ImageDraw.Draw(img, "RGBA"),
                cx + radius - r, cy + radius - r, max(4, int(r * 0.72)),
            )

    def _paint_watermark(self, img: Image.Image, config: ChatConfig, total: int) -> None:
        """Ненавязчивая пометка о вымышленном характере переписки.

        Рисуется ТОЛЬКО если пользователь её включил. Раньше здесь был
        запасной вариант ``or self.t.watermark_text``, из-за которого
        пометка появлялась даже при пустом значении.
        """
        text = (config.disclaimer or "").strip()
        if not text:
            return
        size = int(self.t.font_meta * 0.92)
        y = total - int(self.t.font_meta * 3.6)
        D.watermark_pill(
            img, self.width // 2, max(y, self.header_height + 6), text,
            self.fm, size, self.t.watermark_fg, self.t.watermark_bg, alpha=150,
            radius=int(size * 0.9),
        )

    # --- Отрисовка сообщений (проход 2) -----------------------------
    def paint_message(
        self, img: Image.Image, draw, lay: Layout, config: ChatConfig, y: int
    ) -> int:
        """Отрисовать одно сообщение; вернуть новую координату Y."""
        if lay.kind == MessageKind.DATE:
            return self._paint_date(draw, lay, y)
        if lay.kind == MessageKind.SERVICE:
            return self._paint_service(draw, lay, y)
        if lay.kind == MessageKind.STICKER:
            return self._paint_sticker(img, draw, lay, config, y)
        return self._paint_bubble(img, draw, lay, config, y)

    def _bubble_colors(self, is_out: bool):
        color = self.t.out_bg if is_out else self.t.in_bg
        text_color = self.t.out_text if is_out else self.t.in_text
        meta_color = self.t.out_meta if is_out else self.t.in_meta
        return color, text_color, meta_color

    def _bubble_x(self, w: int, is_out: bool) -> int:
        left = self.t.side_margin + self.avatar_reserved(0)
        if not is_out:
            return left
        right = self.width - self.t.side_margin
        tail = self.t.bubble_tail if self.settings.show_tail else 0
        return max(left, right - w - tail)

    # --- Пузырь с текстом/медиа --------------------------------------
    def _paint_bubble(self, img, draw, lay: Layout, config: ChatConfig, y: int) -> int:
        message = lay.message
        is_out = lay.side == 1
        pad_x, pad_y = self.t.pad_x, self.t.pad_y
        radius = self.t.bubble_radius
        tail = self.t.bubble_tail if lay.tail else 0

        w = lay.width
        reaction_h = int(lay.extra.get("reaction_h", 0))
        # Пузырь рисуется на ПОЛНУЮ высоту, включая место под реакцию:
        # раньше здесь вычитался reaction_h, и пилюля реакции оказывалась
        # под пузырём отдельной плашкой вместо его нижнего края.
        body_h = lay.height
        x = self._bubble_x(w, is_out)
        color, text_color, meta_color = self._bubble_colors(is_out)

        if not is_out and self.t.avatar_in_messages:
            self._paint_avatar(
                img,
                self.t.side_margin + self.t.avatar_size // 2,
                y + self.t.avatar_size // 2,
                self.t.avatar_size // 2,
                self._participant(config, message),
            )

        shadow = self.t.out_shadow if is_out else self.t.in_shadow
        D.drop_shadow(img, (x, y, w, body_h), radius, shadow, 3, 9)
        D.bubble_with_tail(img, (x, y, w, body_h), color, radius, lay.side, tail)

        cursor = y + pad_y
        inner_x = x + pad_x
        inner_w = w - 2 * pad_x

        if message.kind == MessageKind.FORWARD and message.forward_from:
            cursor = self._paint_forward(draw, message, inner_x, cursor, inner_w, is_out)
        if lay.quote_lines:
            cursor = self._paint_quote(draw, lay, inner_x, cursor, inner_w, is_out)
        if lay.media_box:
            mw, mh = lay.media_box
            cursor = self._paint_media(img, draw, lay, inner_x, cursor, mw, mh, is_out)

        line_h = self.t.message_line_height
        for line in lay.lines:
            self.fm.draw_text(
                draw, (inner_x, cursor), line, self.t.font_message, text_color + (255,)
            )
            cursor += line_h

        self._paint_meta(draw, lay, x, y, cursor, line_h, w, pad_x, meta_color, is_out)

        # Реакция — поверх нижнего края пузыря, как в настоящем Telegram.
        if reaction_h and message.reaction:
            self._paint_reaction(draw, lay, x, y + body_h - reaction_h, w, is_out)
        return y + lay.height

    def _paint_forward(
        self, draw, message: Message, x: int, y: int, width: int, is_out: bool
    ) -> int:
        fg = self.t.forward_fg_out if is_out else self.t.forward_fg_in
        size = int(self.t.font_meta * 0.95)
        # Стрелка рисуется текстом, а не символом: часть шрифтов
        # отображает «↪» как цветной emoji-бокс.
        label = f"Переслано от {message.forward_from}"
        label = fit_single_line(label, self.fm, size, width)
        self.fm.draw_text(draw, (x, y), label, size, fg + (255,))
        return y + int(self.t.font_meta * 1.75)

    def _paint_meta(
        self, draw, lay: Layout, x: int, y: int, cursor: int, line_h: int,
        w: int, pad_x: int, meta_color, is_out: bool,
    ) -> None:
        """Время и галочки прочтения в правом нижнем углу пузыря."""
        meta_w = int(lay.extra.get("time_w", 0))
        if not meta_w:
            return
        message = lay.message
        size = int(lay.extra.get("time_size", self.t.font_meta))
        checks_w = self.checks_width(message)

        # Правая граница служебного блока
        right = x + w - pad_x
        time_x = right - meta_w
        if lay.lines:
            meta_y = cursor - line_h + int(line_h * 0.40)
        else:
            # Медиа: время в правом нижнем углу внутри пузыря
            body_h = int(lay.extra.get("body_h") or 0)
            meta_y = y + body_h - self.t.pad_y - int(size * 0.9)

        self.fm.draw_text(
            draw, (time_x, meta_y), message.time or "", size, meta_color + (255,)
        )
        if checks_w:
            check_size = self.check_size()
            color = (
                self.t.out_check_read
                if (message.read and self.t.show_read_double)
                else self.t.out_check
            )
            D.draw_checks(
                draw,
                right - int(check_size * 1.62),
                meta_y + int(size * 0.18),
                check_size, color, double=self.t.show_read_double,
            )

    def _participant(self, config: ChatConfig, message: Message) -> Optional[Participant]:
        idx = message.author_index
        if 0 <= idx < len(config.participants):
            return config.participants[idx]
        return None

    def _paint_quote(
        self, draw, lay: Layout, x: int, y: int, width: int, is_out: bool
    ) -> int:
        """Блок «ответ на сообщение» внутри пузыря."""
        meta = int(self.t.font_meta)
        name_color = self.t.quote_name_out if is_out else self.t.quote_name_in
        text_color = self.t.quote_text_out if is_out else self.t.quote_text_in
        bar = self.t.quote_bar_out if is_out else self.t.quote_bar_in

        lines = lay.quote_lines
        block_h = int(meta * 2.0) + len(lines) * int(meta * 1.32)
        block_w = max(60, int(width * 0.92))
        name = fit_single_line(lay.quote_name or "", self.fm, self.t.font_name, block_w - 16)
        self.fm.draw_text(draw, (x, y), name, self.t.font_name, name_color + (255,))

        cy = y + int(meta * 1.75)
        for line in lines:
            self.fm.draw_text(draw, (x, cy), line, int(meta * 1.05), text_color + (255,))
            cy += int(meta * 1.32)
        bar_w = max(4, int(meta * 0.18))
        draw.rectangle([x, y, x + bar_w, y + block_h], fill=bar + (255,))
        return y + block_h + int(self.t.pad_y * 0.55)

    def _paint_media(
        self, img, draw, lay: Layout, x: int, y: int, w: int, h: int, is_out: bool
    ) -> int:
        """Изображение, голосовое или файл внутри пузыря."""
        if lay.kind == MessageKind.IMAGE:
            return self._paint_image(img, draw, lay, x, y, w, h, is_out)
        if lay.kind == MessageKind.VOICE:
            return self._paint_voice(draw, lay, x, y, w, h, is_out)
        return self._paint_file(draw, lay, x, y, w, h, is_out)

    def _paint_image(
        self, img, draw, lay: Layout, x: int, y: int, w: int, h: int, is_out: bool
    ) -> int:
        media = lay.message.media
        photo = F.safe_open(media.path) if media and media.path else None
        if photo is not None:
            D.paste_rounded(img, photo, (x, y, w, h), radius=18)
        else:
            seed = abs(hash(lay.message.id)) % 7
            top = D.mix(self.t.in_bg, self.t.header_accent, 0.45)
            bottom = D.mix(self.t.in_bg, self.t.header_accent, 0.15)
            placeholder = D.photo_placeholder(
                (w, h), top, bottom, self.t.header_fg, self.fm,
                label=(media.caption[:40] if media and media.caption else "🖼 Фото"),
                seed=seed,
            )
            D.paste_rounded(img, placeholder, (x, y, w, h), radius=18)
        _ = is_out
        return y + h + int(self.t.pad_y * 0.7)

    def _paint_voice(
        self, draw, lay: Layout, x: int, y: int, w: int, h: int, is_out: bool
    ) -> int:
        """Голосовое сообщение: кнопка play, звуковая дорожка, длительность."""
        media = lay.message.media
        is_unread = is_out and not lay.message.read
        size = int(self.t.font_meta * 0.95)
        duration = (media.duration if media else "0:12") or "0:12"

        r = int(h * 0.32)
        cx, cy = x + r + int(self.t.pad_x * 0.35), y + h // 2
        D.play_button(draw, (cx, cy), r, self.t.header_accent, (255, 255, 255))

        dur_w = int(self.fm.measure(duration, size))
        checks = self.checks_width(lay.message) if is_unread else 0
        right_pad = int(self.t.pad_x * 0.4)

        bar_x = cx + r + int(self.t.pad_x * 0.45)
        dur_x = x + w - right_pad - dur_w - (checks + int(size * 0.35) if checks else 0)
        bar_w = max(20, int(dur_x - size * 0.4 - bar_x))

        D.waveform(
            draw, (bar_x, y + int(h * 0.26), bar_w, int(h * 0.48)),
            self.t.out_check_read if is_unread else self.t.in_meta,
            seed=abs(hash(lay.message.id)) % 17,
        )
        self.fm.draw_text(
            draw, (dur_x, cy - size // 2), duration, size,
            (self.t.out_meta if is_out else self.t.in_meta) + (255,),
        )
        if checks:
            check_size = self.check_size()
            D.draw_checks(
                draw, x + w - right_pad - int(check_size * 1.62),
                cy - check_size // 2, check_size, self.t.out_check_read, double=True,
            )
        return y + h + int(self.t.pad_y * 0.7)

    def _paint_file(
        self, draw, lay: Layout, x: int, y: int, w: int, h: int, is_out: bool
    ) -> int:
        media = lay.message.media
        name = fit_single_line(
            (media.file_name if media else "") or "Файл",
            self.fm, int(self.t.font_meta * 1.05), w - int(self.t.font_meta * 4.6),
        )
        size_text = (media.file_size if media else "") or ""
        icon = int(self.t.font_meta * 2.1)
        D.file_icon(
            draw, (x, y + (h - icon) // 2, int(icon * 0.78), icon), self.t.header_accent
        )
        text_color = self.t.in_text if not is_out else self.t.out_text
        meta_color = self.t.in_meta if not is_out else self.t.out_meta
        tx = x + int(icon * 1.15)
        self.fm.draw_text(
            draw, (tx, y + h * 0.24), name, int(self.t.font_meta * 1.05), text_color + (255,)
        )
        if size_text:
            self.fm.draw_text(
                draw, (tx, y + h * 0.56), size_text, int(self.t.font_meta * 0.95),
                meta_color + (255,),
            )
        return y + h + int(self.t.pad_y * 0.7)

    def _paint_reaction(
        self, draw, lay: Layout, x: int, y: int, w: int, is_out: bool
    ) -> None:
        """Пилюля с реакцией в нижнем краю пузыря.

        Раньше ``py`` сдвигался вверх на ``pill_h // 4``, из-за чего пилюля
        свешивалась ниже пузыря. Теперь она выровнена по нижнему краю
        пузыря и лежит внутри него, как в настоящем Telegram.
        """
        reaction = lay.message.reaction
        if reaction is None:
            return
        size = int(self.t.font_meta * 0.9)
        text = f"{reaction.emoji} {reaction.count}" if reaction.count > 1 else reaction.emoji
        pad_x = int(size * 0.8)
        pill_w = int(self.fm.measure(text, size)) + pad_x * 2
        pill_h = int(size * 1.9)
        px = (x + w - pill_w) if is_out else x
        # y передаётся как верх зарезервированной полосы под реакцией.
        # Раньше здесь вычиталась половина ВСЕЙ высоты пузыря, из-за чего
        # пилюля уезжала в середину пузыря и перекрывала текст.
        band = int(lay.extra.get("reaction_h", pill_h))
        py = max(0, y - (band - pill_h) // 2)

        if reaction.mine:
            bg, fg = self.t.reaction_self_bg, self.t.reaction_self_fg
        else:
            bg, fg = self.t.reaction_bg, self.t.reaction_fg
        draw.rounded_rectangle(
            [px, py, px + pill_w, py + pill_h], radius=pill_h // 2,
            fill=bg + (255,), outline=self.t.reaction_border + (255,), width=2,
        )
        self.fm.draw_text(
            draw, (px + pill_w // 2, py + pill_h // 2 - size // 2), text,
            size, fg + (255,), anchor="ma",
        )

    def _paint_date(self, draw, lay: Layout, y: int) -> int:
        """Разделитель дат."""
        pill_h = int(lay.extra.get("pill_h", 40))
        size = int(lay.extra.get("font_size", 26))
        text = lay.message.text or lay.message.date_label or "Сегодня"
        w = int(self.fm.measure(text, size)) + int(size * 2.4)
        x = (self.width - w) // 2
        ty = y + int(self.t.font_meta * 0.8)
        draw.rounded_rectangle(
            [x, ty, x + w, ty + pill_h], radius=pill_h // 2, fill=self.t.date_bg + (255,)
        )
        self.fm.draw_text(
            draw, (x + w // 2, ty + pill_h // 2 - size // 2), text,
            size, self.t.date_fg + (255,), anchor="ma",
        )
        return y + lay.height

    def _paint_service(self, draw, lay: Layout, y: int) -> int:
        """Системное сообщение по центру."""
        size = int(lay.extra.get("font_size", 26))
        line_h = int(lay.extra.get("line_h", int(size * 1.35)))
        text_lines = lay.lines or [lay.message.text or ""]
        block_h = line_h * len(text_lines) + int(size * 1.1)
        w = int(
            max((self.fm.measure(line, size) for line in text_lines), default=0)
        ) + int(size * 2.2)
        x = (self.width - w) // 2
        ty = y + int(self.t.font_meta * 0.6)
        draw.rounded_rectangle(
            [x, ty, x + w, ty + block_h], radius=int(block_h / 2),
            fill=self.t.service_bg + (170,),
        )
        cy = ty + int(size * 0.55)
        for line in text_lines:
            self.fm.draw_text(
                draw, (x + w // 2, cy), line, size, self.t.service_fg + (255,), anchor="ma"
            )
            cy += line_h
        return y + lay.height

    def _paint_sticker(self, img, draw, lay: Layout, config: ChatConfig, y: int) -> int:
        """Стикер (реальное фото или mock-карточка с эмодзи)."""
        size = int(lay.extra.get("sticker_size", 300))
        is_out = lay.side == 1
        x = self._bubble_x(size, is_out)
        media = lay.message.media
        photo = F.safe_open(media.path) if media and media.path else None
        if photo is not None:
            D.paste_rounded(img, photo, (x, y, size, size), radius=int(size * 0.12))
        else:
            card = D.sticker_card(
                size, (media.emoji if media else "🙂") or "🙂", self.fm,
                gradient_index=abs(hash(lay.message.id)) % 5,
            )
            D.paste_rounded(img, card, (x, y, size, size), radius=int(size * 0.12))
        if lay.message.text:
            size_meta = int(self.t.font_meta)
            lines = wrap_text(lay.message.text, self.fm, size_meta, size)
            cy = y + size + int(self.t.font_meta * 0.5)
            color = self.t.out_meta if is_out else self.t.in_meta
            for line in lines:
                self.fm.draw_text(draw, (x, cy), line, size_meta, color + (255,))
                cy += int(size_meta * 1.35)
        _ = config
        return y + lay.height


__all__ = ["BaseRenderer", "Layout"]
