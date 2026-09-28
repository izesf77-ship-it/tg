"""Схема шаблона (демонстрационная вымышленная история)."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class TemplatePreview(BaseModel):
    """Превью шаблона для кнопки в интерфейсе."""

    model_config = ConfigDict(extra="ignore")

    key: str
    title: str
    emoji: str
    description: str
    preview: str = ""
    participants: List[str] = Field(default_factory=list)
    message_count: int = 0
    premium_only: bool = False
    style: Optional[str] = None


__all__ = ["TemplatePreview"]
