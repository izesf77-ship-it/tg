"""Сервис генерации изображений переписки."""

from __future__ import annotations

import asyncio
import io
import logging
import time
from typing import Optional

from bot.config import settings
from bot.generators import get_renderer
from bot.schemas import ChatConfig
from bot.utils import files as F
from bot.utils.errors import RenderError

logger = logging.getLogger(__name__)


class RenderService:
    """Рендерит переписку в PNG, учитывая лимиты и логирование."""

    async def render_bytes(
        self,
        config: ChatConfig,
        style: Optional[str] = None,
        fmt: str = "PNG",
    ) -> bytes:
        return await asyncio.to_thread(self._render_sync, config, style, fmt)

    def _render_sync(
        self, config: ChatConfig, style: Optional[str], fmt: str
    ) -> bytes:
        started = time.perf_counter()
        use_style = style or config.style
        try:
            renderer = get_renderer(use_style, width=settings.render_width)
            image = renderer.render(config)
            buffer = io.BytesIO()
            image.save(buffer, format=fmt, optimize=True)
            data = buffer.getvalue()
        except MemoryError as exc:
            raise RenderError("Переписка слишком большая для генерации.") from exc
        except RenderError:
            raise
        except Exception as exc:  # noqa: BLE001 - Pillow может бросить что угодно
            logger.exception("Ошибка рендера (style=%s)", use_style)
            raise RenderError(f"Не удалось отрисовать изображение: {exc}") from exc

        elapsed = (time.perf_counter() - started) * 1000
        logger.info(
            "Сгенерировано изображение: style=%s, сообщений=%s, размер=%dx%d, "
            "%.0f КБ, %.0f мс",
            use_style, len(config.messages), image.width, image.height,
            len(data) / 1024, elapsed,
        )
        return data

    async def render_to_file(
        self, config: ChatConfig, style: Optional[str] = None
    ) -> bytes:
        """Отрендерить и сохранить копию в data/renders (для отладки)."""
        data = await self.render_bytes(config, style)
        F.ensure_dirs()
        name = f"chat_{int(time.time())}_{len(config.messages)}msg.png"
        try:
            (settings.renders_dir / name).write_bytes(data)
            F.cleanup_renders(50)
        except OSError as exc:  # pragma: no cover
            logger.debug("Не удалось сохранить рендер: %s", exc)
        return data


render_service = RenderService()

__all__ = ["RenderService", "render_service"]
