"""Файловый слой: медиа пользователей, рендеры, безопасная работа с изображениями."""

from __future__ import annotations

import hashlib
import logging
import secrets
import shutil
from pathlib import Path
from typing import Tuple

from PIL import Image, UnidentifiedImageError

from bot.config import settings

logger = logging.getLogger(__name__)

MAX_MEDIA_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def ensure_dirs() -> None:
    settings.setup_dirs()


def media_dir(chat_key: str | int | None = None) -> Path:
    base = settings.media_dir
    if chat_key is None:
        return base
    safe = "".join(ch for ch in str(chat_key) if ch.isalnum() or ch in "-_")[:64] or "shared"
    path = base / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_media_path(chat_key: str | int, suffix: str = ".jpg") -> Path:
    if suffix not in IMAGE_SUFFIXES:
        suffix = ".jpg"
    token = secrets.token_hex(8)
    digest = hashlib.sha1(f"{chat_key}:{token}".encode()).hexdigest()[:8]
    return media_dir(chat_key) / f"{digest}_{token}{suffix}"


def delete_media(chat_key: str | int) -> None:
    """Delete the media directory for one user/chat key."""
    base = settings.media_dir.resolve()
    safe = "".join(
        ch for ch in str(chat_key) if ch.isalnum() or ch in "-_"
    )[:64] or "shared"
    path = (base / safe).resolve()
    if path.parent != base or not path.is_dir():
        return
    shutil.rmtree(path)


def save_bytes(data: bytes, chat_key: str | int, suffix: str = ".jpg") -> Path | None:
    """Сохранить байты изображения на диск. None — если данные некорректны."""
    if not data:
        return None
    if len(data) > MAX_MEDIA_BYTES:
        logger.warning("Медиа слишком большое: %s байт", len(data))
        return None
    path = new_media_path(chat_key, suffix)
    try:
        path.write_bytes(data)
    except OSError as exc:
        logger.error("Не удалось сохранить медиа %s: %s", path, exc)
        return None
    return path


def is_image_bytes(data: bytes) -> bool:
    if not data:
        return False
    try:
        with Image.open(__import__("io").BytesIO(data)) as img:
            width, height = img.size
            if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                return False
            img.verify()
        return True
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        return False


def probe_image(path: str | Path) -> Tuple[int, int] | None:
    """Размер изображения или None, если файл битый/отсутствует."""
    try:
        p = Path(path)
        if not p.exists() or p.stat().st_size == 0:
            return None
        with Image.open(p) as img:
            if img.width <= 0 or img.height <= 0 or img.width * img.height > MAX_IMAGE_PIXELS:
                return None
            img.load()
            return img.size
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        OSError,
        ValueError,
        MemoryError,
    ) as exc:
        logger.warning("Битое изображение %s: %s", path, exc)
        return None


def safe_open(path: str | Path) -> Image.Image | None:
    """Открыть изображение в RGB/RGBA. None при любой ошибке."""
    try:
        p = Path(path)
        if not p.exists() or p.stat().st_size == 0:
            return None
        with Image.open(p) as img:
            if (
                img.width <= 0
                or img.height <= 0
                or img.width * img.height > MAX_IMAGE_PIXELS
            ):
                return None
            img.load()
            return img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        OSError,
        ValueError,
        MemoryError,
    ) as exc:
        logger.warning("Не удалось открыть изображение %s: %s", path, exc)
        return None


def guess_suffix(filename: str | None) -> str:
    if not filename:
        return ".jpg"
    suffix = Path(filename).suffix.lower()
    return suffix if suffix in IMAGE_SUFFIXES else ".jpg"


def cleanup_renders(keep_last: int = 50) -> None:
    """Удалить старые рендеры, оставив последние ``keep_last``."""
    folder: Path = settings.renders_dir
    if not folder.exists():
        return
    try:
        files = sorted(folder.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return
    for old in files[keep_last:]:
        try:
            old.unlink()
        except OSError:
            pass


__all__ = [
    "MAX_MEDIA_BYTES",
    "MAX_IMAGE_PIXELS",
    "IMAGE_SUFFIXES",
    "ensure_dirs",
    "media_dir",
    "new_media_path",
    "delete_media",
    "save_bytes",
    "is_image_bytes",
    "probe_image",
    "safe_open",
    "guess_suffix",
    "cleanup_renders",
]
