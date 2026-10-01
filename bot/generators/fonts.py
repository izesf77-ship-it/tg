"""Поиск и загрузка шрифтов.

Порядок поиска:
1. Каталог ``fonts/`` проекта (приоритет — по имени файла).
2. Системные каталоги шрифтов (Windows / macOS / Linux).
3. Встроенный шрифт Pillow как последний резерв.

Кириллица проверяется автоматически: если в найденном шрифте нет
русских букв, берётся следующий кандидат. Emoji обрабатываются
отдельным цветным/монохромным шрифтом.
"""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from bot.config import settings

logger = logging.getLogger(__name__)

# --- Приоритетные имена файлов шрифтов -------------------------
# (regular, medium, bold) — подбираются по «публичным» именам.
PRIORITY_SETS: Tuple[Tuple[str, str, str], ...] = (
    ("Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-Bold.ttf"),
    ("Inter.ttf", "Inter-Medium.ttf", "Inter-Bold.ttf"),
    ("Roboto-Regular.ttf", "Roboto-Medium.ttf", "Roboto-Bold.ttf"),
    ("Roboto.ttf", "Roboto-Medium.ttf", "Roboto-Bold.ttf"),
    ("NotoSans-Regular.ttf", "NotoSans-Medium.ttf", "NotoSans-Bold.ttf"),
    ("NotoSans.ttf", "NotoSans-Medium.ttf", "NotoSans-Bold.ttf"),
    ("OpenSans-Regular.ttf", "OpenSans-SemiBold.ttf", "OpenSans-Bold.ttf"),
    ("Montserrat-Regular.ttf", "Montserrat-Medium.ttf", "Montserrat-Bold.ttf"),
    ("Rubik-Regular.ttf", "Rubik-Medium.ttf", "Rubik-Bold.ttf"),
    ("Manrope-Regular.ttf", "Manrope-Medium.ttf", "Manrope-Bold.ttf"),
    ("SegoeUI.ttf", "SegoeUI-Semibold.ttf", "SegoeUI-Bold.ttf"),
    ("arial.ttf", "arialbd.ttf", "arialbd.ttf"),
    ("verdana.ttf", "verdanab.ttf", "verdanab.ttf"),
    ("tahoma.ttf", "tahomabd.ttf", "tahomabd.ttf"),
    ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"),
    ("FreeSans.ttf", "FreeSansBold.ttf", "FreeSansBold.ttf"),
)

EMOJI_CANDIDATES: Tuple[str, ...] = (
    "NotoColorEmoji.ttf",
    "NotoEmoji-Regular.ttf",
    "NotoEmojiMono-Regular.ttf",
    "seguiemj.ttf",
    "SegoeUI Emoji.ttf",
    "AppleColorEmoji.ttc",
    "Symbola.ttf",
    "SegoeUISymbol.ttf",
    "seguisym.ttf",
    "NotoSansSymbols2-Regular.ttf",
)

SYSTEM_FONT_DIRS: Dict[str, Tuple[str, ...]] = {
    "win32": (
        "C:/Windows/Fonts",
        str(Path.home() / "AppData/Local/Microsoft/Windows/Fonts"),
    ),
    "darwin": (
        "/System/Library/Fonts",
        "/Library/Fonts",
        str(Path.home() / "Library/Fonts"),
    ),
    "linux": (
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        str(Path.home() / ".fonts"),
        str(Path.home() / ".local/share/fonts"),
    ),
}

# Диапазоны emoji (упрощённые, покрывают основные сюжеты)
EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"  # Supplementary Symbols & Pictographs
    "\U0001F1E0-\U0001F1FF"  # Flags
    "☀-➿"      # Dingbats, arrows, misc symbols
    "⬀-⯿"      # Misc Symbols and Arrows
    "←-⇿"      # Supplemental Arrows
    "⌀-⏿"      # Misc Technical
    "︀-️"      # VS
    "-‏"      # ZWJ, LRM и пр.
    "©®™"
    "]+"
)

CYRILLIC_PROBE = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя"


def is_emoji_char(ch: str) -> bool:
    return ch == "\u200d" or (ch != "-" and bool(EMOJI_RE.match(ch)))


def split_emoji_runs(text: str) -> List[Tuple[str, bool]]:
    """Разбить текст на чередующиеся участки: (фрагмент, это_emoji?)."""
    runs: List[Tuple[str, bool]] = []
    buf = ""
    buf_emoji: Optional[bool] = None
    for ch in text:
        cur = is_emoji_char(ch)
        if buf_emoji is None or cur == buf_emoji:
            buf += ch
            buf_emoji = cur
        else:
            runs.append((buf, bool(buf_emoji)))
            buf = ch
            buf_emoji = cur
    if buf:
        runs.append((buf, bool(buf_emoji)))
    return runs


def has_emoji(text: str) -> bool:
    return bool(text) and bool(EMOJI_RE.search(text))


@dataclass
class EmojiFontInfo:
    """Информация о шрифте emoji."""

    path: Optional[Path] = None
    name: str = ""
    color: bool = False
    native_size: int = 109
    scalable: bool = True

    @property
    def available(self) -> bool:
        return self.path is not None


class FontManager:
    """Загрузка, кэширование и отрисовка текста с поддержкой emoji."""

    def __init__(self, fonts_dir: Path | None = None) -> None:
        self.fonts_dir = Path(fonts_dir or settings.fonts_path)
        self._cache: Dict[Tuple[int, str], ImageFont.FreeTypeFont] = {}
        self._fallback: Optional[object] = None
        self._emoji_font_obj: Optional[ImageFont.FreeTypeFont] = None
        self._emoji_width_cache: Dict[Tuple[str, int], float] = {}
        self.text_paths: Dict[str, Path] = {}
        self.emoji: EmojiFontInfo = EmojiFontInfo()
        self.warnings: List[str] = []
        self._discover()

    # --- Поиск файлов ---------------------------------------------
    def _iter_font_files(self) -> Iterator[Path]:
        seen: set = set()

        def add(p: Path) -> Iterator[Path]:
            if p.suffix.lower() not in (".ttf", ".otf", ".ttc", ".otc"):
                return
            try:
                rp = p.resolve()
            except OSError:
                rp = p
            if rp in seen or not p.exists() or not p.is_file():
                return
            seen.add(rp)
            yield p

        if self.fonts_dir.exists():
            try:
                for item in sorted(self.fonts_dir.iterdir()):
                    yield from add(item)
            except OSError:
                pass
        for directory in SYSTEM_FONT_DIRS.get(sys.platform, ()):
            try:
                entries = sorted(Path(directory).rglob("*"))
            except OSError:
                continue
            for item in entries:
                yield from add(item)

    def _discover(self) -> None:
        """Найти текстовый шрифт (с кириллицей) и шрифт emoji."""
        files = list(self._iter_font_files())
        by_lower = {p.name.lower(): p for p in files}

        for name in EMOJI_CANDIDATES:
            path = by_lower.get(name.lower())
            if path:
                info = self._probe_emoji(path)
                if info.available:
                    self.emoji = info
                    break
        if not self.emoji.available:
            self.warnings.append(
                "Шрифт emoji не найден — эмодзи рисуются упрощённо. "
                "Положите NotoColorEmoji.ttf в fonts/."
            )

        candidates: List[Path] = []
        for group in PRIORITY_SETS:
            for name in group:
                path = by_lower.get(name.lower())
                if path:
                    candidates.append(path)
        try:
            custom_root = self.fonts_dir.resolve()
        except OSError:
            custom_root = self.fonts_dir
        for path in files:
            try:
                if path.resolve().parent == custom_root and path not in candidates:
                    candidates.append(path)
            except OSError:
                continue
        if not candidates:
            candidates = files

        chosen: Optional[Path] = None
        for path in candidates:
            if self._probe_cyrillic(path):
                chosen = path
                break
        if chosen is None:
            if candidates:
                chosen = candidates[0]
                self.warnings.append(
                    f"Кириллица в шрифте {chosen.name} не поддерживается."
                )
            else:
                self.warnings.append(
                    "Системные шрифты не найдены, используется шрифт Pillow. "
                    "Положите Inter.ttf / NotoSans.ttf в fonts/ (см. README)."
                )
        if chosen:
            self.text_paths = {"regular": chosen}

    def _probe_cyrillic(self, path: Path) -> bool:
        """Проверить, что шрифт рисует русские буквы."""
        try:
            font = ImageFont.truetype(str(path), 24)
        except (OSError, ValueError):
            return False
        return _renders_text(font, CYRILLIC_PROBE)

    def _probe_emoji(self, path: Path) -> EmojiFontInfo:
        """Определить, цветной ли шрифт emoji и фиксированный ли размер."""
        color = path.name.lower().startswith(
            ("notocoloremoji", "applecoloremoji", "seguiemj")
        )
        native = 109
        scalable = True
        for size in (137, 109, 96, 64):
            try:
                ImageFont.truetype(str(path), size)
                native = size
                break
            except OSError:
                continue
        else:
            return EmojiFontInfo()
        if not color:
            try:
                ImageFont.truetype(str(path), 24)
            except OSError:
                scalable = False
        if not _renders_emoji(path, size=min(native, 48)):
            return EmojiFontInfo()
        return EmojiFontInfo(path=path, name=path.name, color=color,
                             native_size=native, scalable=scalable)

    # --- Доступ к шрифтам -----------------------------------------
    def get(self, size: int, weight: str = "regular"):
        """Основной текстовый шрифт нужного размера (с кэшем)."""
        size = max(8, int(size))
        key = (size, weight)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        path = self.text_paths.get("regular")
        if path:
            try:
                font = ImageFont.truetype(str(path), size)
            except (OSError, ValueError) as exc:  # pragma: no cover
                logger.warning("Не удалось загрузить шрифт %s: %s", path, exc)
                font = self._builtin(size)
        else:
            font = self._builtin(size)
        self._cache[key] = font
        return font

    def _builtin(self, size: int):
        """Резервный шрифт Pillow — доступен на любой системе."""
        if self._fallback is None:
            try:
                self._fallback = ImageFont.load_default(size=24)
            except (OSError, TypeError, AttributeError):  # pragma: no cover
                self._fallback = ImageFont.load_default()
        try:
            return ImageFont.load_default(size=size)
        except (OSError, TypeError, AttributeError):  # pragma: no cover
            return self._fallback

    def measure(self, text: str, size: int, weight: str = "regular") -> float:
        """Ширина текста с учётом emoji."""
        if not text:
            return 0.0
        font = self.get(size, weight)
        total = 0.0
        for run, is_em in split_emoji_runs(text):
            if is_em and self.emoji.available:
                total += self.emoji_width(run, size)
            else:
                total += _text_length(font, run)
        return total

    def emoji_width(self, run: str, size: int) -> float:
        """Ширина emoji-фрагмента с учётом фактического шрифта."""
        if not self.emoji.available or not run:
            return 0.0
        target_size = max(8, int(size))
        key = (run, target_size)
        cached = self._emoji_width_cache.get(key)
        if cached is not None:
            return cached

        try:
            font = self._emoji_font(target_size)
            if font is None:
                return 0.0
            if self.emoji.color:
                bbox = font.getbbox(run)
                if bbox:
                    glyph_height = bbox[3] - bbox[1]
                    if glyph_height > 0:
                        width = max(
                            1,
                            int(
                                (bbox[2] - bbox[0])
                                * target_size
                                / glyph_height
                            ),
                        )
                    else:
                        width = target_size
                else:
                    width = target_size
            else:
                width = max(1, int(font.getlength(run)))
        except (OSError, ValueError):
            width = target_size

        self._emoji_width_cache[key] = float(width)
        return float(width)

    def line_height(self, size: int, weight: str = "regular") -> int:
        font = self.get(size, weight)
        try:
            ascent, descent = font.getmetrics()
            return int(ascent + descent)
        except (OSError, AttributeError):  # pragma: no cover
            return int(size * 1.35)

    def draw_text(
        self, draw, xy, text: str, size: int, fill,
        weight: str = "regular", anchor: str = "la",
    ) -> None:
        """Нарисовать текст, подставляя шрифт emoji для emoji-символов."""
        if not text:
            return
        if not has_emoji(text) or not self.emoji.available:
            draw.text(xy, text, font=self.get(size, weight), fill=fill, anchor=anchor)
            return

        x, y = xy
        total = self.measure(text, size, weight)
        h_align = anchor[0] if anchor else "l"
        v_align = anchor[1] if len(anchor) > 1 else "a"
        if h_align == "m":
            x -= total / 2
        elif h_align == "r":
            x -= total
        if v_align == "m":
            y -= size * 0.5
        elif v_align == "s":
            y -= size * 0.8
        elif v_align == "d":
            y -= size * 0.2

        font = self.get(size, weight)
        for run, is_em in split_emoji_runs(text):
            if is_em:
                self._draw_emoji(draw, x, y, run, size, fill)
                x += self.emoji_width(run, size)
            else:
                draw.text((x, y), run, font=font, fill=fill, anchor="la")
                x += _text_length(font, run)

    def info(self) -> Dict[str, str]:
        main = self.text_paths.get("regular")
        return {
            "text_font": main.name if main else "встроенный Pillow",
            "emoji_font": self.emoji.name or "не найден",
            "emoji_color": "да" if self.emoji.color else "нет",
        }


    def _draw_emoji(self, draw, x: float, y: float, run: str, size: int, fill) -> None:
        """Отрисовать emoji-фрагмент (цветной или монохромный)."""
        info = self.emoji
        try:
            if info.color:
                img = self._emoji_image(run, size)
                if img is not None:
                    draw._image.paste(  # type: ignore[attr-defined]
                        img, (int(x), int(y + size * 0.1)), img
                    )
                    return
            draw.text(
                (x, y), run, font=ImageFont.truetype(str(info.path), max(8, int(size))),
                fill=fill, anchor="la",
            )
        except (OSError, ValueError, AttributeError) as exc:  # pragma: no cover
            logger.debug("Emoji-шрифт недоступен (%s), рисуем текстовым", exc)
            draw.text((x, y), run, font=self.get(size), fill=fill, anchor="la")

    def _emoji_image(self, run: str, size: int):
        """Отрисовать цветной emoji в растр нужного размера."""
        info = self.emoji
        try:
            font = self._emoji_font(info.native_size)
            if font is None:
                return None
            bbox = font.getbbox(run)
            if not bbox or bbox[2] - bbox[0] <= 0 or bbox[3] - bbox[1] <= 0:
                return None
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            tmp = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            ImageDraw.Draw(tmp).text(
                (-bbox[0], -bbox[1]), run, font=font, embedded_color=True
            )
            target_h = max(8, int(size))
            scale = target_h / h
            return tmp.resize((max(1, int(w * scale)), target_h), Image.LANCZOS)
        except (OSError, ValueError, MemoryError) as exc:
            logger.debug("Цветной emoji не отрисован: %s", exc)
            return None

    def _emoji_font(self, size: int) -> Optional[ImageFont.FreeTypeFont]:
        """Получить emoji-шрифт, кэшируя bitmap-шрифт в его native size."""
        if not self.emoji.path:
            return None
        if self.emoji.color:
            if self._emoji_font_obj is None:
                self._emoji_font_obj = ImageFont.truetype(
                    str(self.emoji.path), self.emoji.native_size
                )
            return self._emoji_font_obj
        return ImageFont.truetype(str(self.emoji.path), max(8, int(size)))


def _is_variation(ch: str) -> bool:
    """Служебные символы (VS16, ZWJ, направления) не занимают ширину."""
    return ch in {"️", "︎", "‍", "‌", "‎", "‏"}


def _text_length(font, text: str) -> float:
    try:
        return float(font.getlength(text))
    except (AttributeError, OSError, ValueError):  # pragma: no cover
        bbox = font.getbbox(text)
        return float(bbox[2] - bbox[0])


def _renders_text(font, sample: str) -> bool:
    """True, если шрифт реально рисует символы (а не пустые рамки)."""
    try:
        width = _text_length(font, sample)
        if width <= 0:
            return False
        img = Image.new("L", (int(width) + 8, 48), 0)
        ImageDraw.Draw(img).text((2, 2), sample, font=font, fill=255)
        return img.getbbox() is not None
    except (OSError, ValueError):
        return False


def _renders_emoji(path: Path, size: int = 48) -> bool:
    try:
        font = ImageFont.truetype(str(path), size)
    except OSError:
        return False
    try:
        img = Image.new("L", (size * 2, size * 2), 0)
        ImageDraw.Draw(img).text((2, 2), "\U0001f642", font=font, fill=255)
        return img.getbbox() is not None
    except (OSError, ValueError):
        return False


def get_font_manager(fonts_dir: str | None = None) -> FontManager:
    """Менеджер шрифтов (создаётся один раз на каталог)."""
    manager = FontManager(Path(fonts_dir) if fonts_dir else None)
    logger.info("Шрифты: %s", manager.info())
    for warning in manager.warnings:
        logger.warning("%s", warning)
    return manager


__all__ = [
    "FontManager",
    "EmojiFontInfo",
    "get_font_manager",
    "has_emoji",
    "is_emoji_char",
    "split_emoji_runs",
    "EMOJI_CANDIDATES",
    "PRIORITY_SETS",
]
