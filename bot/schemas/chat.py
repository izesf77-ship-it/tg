"""Схемы переписки.

Участник ``side``:
* ``0`` — собеседник (сообщения слева),
* ``1`` — пользователь/второй участник (сообщения справа).

Благодаря явному ``side`` один и тот же участник может участвовать
с любой стороны, как в реальных чатах.
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from bot.utils import text_utils as T
from bot.utils.time_utils import current_time_str

MAX_MESSAGES = 500


class MessageKind(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VOICE = "voice"
    FILE = "file"
    STICKER = "sticker"
    SERVICE = "service"
    DATE = "date"
    FORWARD = "forward"


class Reaction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    emoji: str = "👍"
    count: int = 1
    mine: bool = True

    @field_validator("emoji")
    @classmethod
    def _emoji(cls, v: str) -> str:
        v = T.clamp(v or "👍", 8)
        return v or "👍"


class MediaItem(BaseModel):
    """Медиа-элемент. Хранится путь к локальному файлу (если он есть)."""

    model_config = ConfigDict(extra="ignore")

    kind: MessageKind = MessageKind.IMAGE
    path: Optional[str] = None
    width: int = 0
    height: int = 0
    caption: str = ""
    duration: str = "0:12"
    file_name: str = "file.pdf"
    file_size: str = "2,4 МБ"
    emoji: str = "🩻"
    gradient: int = 0

    def to_json(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")


class Participant(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = "Участник"
    username: str = ""
    display_name: str = ""
    avatar_path: Optional[str] = None
    status: str = "в сети"
    last_seen: str = "12:41"
    premium: bool = False
    verified: bool = False
    side: int = 0
    color: str = ""
    last_seen_label: str = ""

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = T.clamp(v, T.MAX_NAME_LENGTH)
        return v or "Участник"

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        return T.ensure_username(v) if v else ""

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        v = T.clamp(v, T.MAX_STATUS_LENGTH)
        return v or "в сети"

    @property
    def title(self) -> str:
        """Имя в шапке чата: display_name приоритетнее."""
        return self.display_name or self.name

    @property
    def short_name(self) -> str:
        return T.truncate_preview(self.name, 24) or "Участник"

    def mention(self) -> str:
        return f"@{self.username}" if self.username else self.name

    def status_line(self) -> str:
        if self.status == "был(а) недавно" and self.last_seen:
            return f"был(а) в сети сегодня в {self.last_seen}"
        return self.status

    def to_json(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")


class Message(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    kind: MessageKind = MessageKind.TEXT
    text: str = ""
    time: str = Field(default_factory=current_time_str)
    side: int = 0
    author_index: int = 0
    reply_to: Optional[str] = None
    forward_from: str = ""
    read: bool = True
    reaction: Optional[Reaction] = None
    media: Optional[MediaItem] = None
    date_label: str = ""
    edited: bool = False

    @field_validator("time")
    @classmethod
    def _time(cls, v: str) -> str:
        """Нормализует время; при неудаче оставляет пустым (рисуется по умолчанию)."""
        from bot.utils.time_utils import current_time_str, is_valid_time

        v = str(v or "").strip()
        if not v:
            return current_time_str()
        return v if is_valid_time(v) else current_time_str()

    @field_validator("side")
    @classmethod
    def _side(cls, v: int) -> int:
        """Сторона сообщения строго 0 (слева) или 1 (справа)."""
        return 1 if int(v) == 1 else 0

    @field_validator("author_index")
    @classmethod
    def _author(cls, v: int) -> int:
        return max(0, int(v))

    @field_validator("text")
    @classmethod
    def _text(cls, v: str) -> str:
        return T.clamp_multiline(v, T.MAX_MESSAGE_LENGTH)

    @field_validator("forward_from")
    @classmethod
    def _forward(cls, v: str) -> str:
        return T.clamp(v, 64)

    @property
    def is_media(self) -> bool:
        return self.kind in (
            MessageKind.IMAGE,
            MessageKind.VOICE,
            MessageKind.FILE,
            MessageKind.STICKER,
        )

    @property
    def is_service(self) -> bool:
        return self.kind in (MessageKind.SERVICE, MessageKind.DATE)

    def type_icon(self) -> str:
        return {
            MessageKind.TEXT: "💬",
            MessageKind.IMAGE: "🖼",
            MessageKind.VOICE: "🎤",
            MessageKind.FILE: "📎",
            MessageKind.STICKER: "🩻",
            MessageKind.SERVICE: "ℹ️",
            MessageKind.DATE: "📅",
            MessageKind.FORWARD: "↪️",
        }.get(self.kind, "💬")

    def preview(self, limit: int = 60) -> str:
        if self.kind == MessageKind.SERVICE:
            return T.truncate_preview(self.text, limit)
        if self.kind == MessageKind.DATE:
            return T.truncate_preview(self.text or self.date_label, limit)
        media = self.media
        if self.kind == MessageKind.VOICE:
            base = f"Голосовое {media.duration if media else '0:12'}"
        elif self.kind == MessageKind.FILE:
            base = f"Файл {media.file_name if media else ''}"
        elif self.kind == MessageKind.STICKER:
            base = f"Стикер {media.emoji if media else ''}"
        elif self.kind == MessageKind.IMAGE:
            cap = media.caption if media else ""
            base = f"🖼 {cap}" if cap else "🖼 Фотография"
        else:
            base = self.text
        return T.truncate_preview(base, limit)

    def to_json(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "Message":
        return cls.model_validate(data)


class ChatSettings(BaseModel):
    """Настройки отображения переписки."""

    model_config = ConfigDict(extra="ignore")

    show_time: bool = True
    show_checks: bool = True
    show_read: bool = True
    show_reactions: bool = True
    show_avatars_in_header: bool = True
    show_tail: bool = True
    show_pattern: bool = True
    date_dividers: bool = True
    header_status: bool = True
    bubble_max_ratio: float = 0.76
    max_messages: int = 200

    @field_validator("bubble_max_ratio")
    @classmethod
    def _ratio(cls, v: float) -> float:
        return min(0.92, max(0.45, float(v)))

    @field_validator("max_messages")
    @classmethod
    def _max(cls, v: int) -> int:
        return min(MAX_MESSAGES, max(1, int(v)))


class ChatConfig(BaseModel):
    """Полная конфигурация переписки (хранится в БД как JSON)."""

    model_config = ConfigDict(extra="ignore")

    title: str = "Переписка"
    style: str = "telegram"
    participants: List[Participant] = Field(default_factory=list)
    messages: List[Message] = Field(default_factory=list)
    settings: ChatSettings = Field(default_factory=ChatSettings)
    created_at: str = ""
    template: str = ""
    # Пометка о вымышленном характере переписки.
    # По умолчанию ВЫКЛЮЧЕНА (пустая строка) — включается в настройках
    # переписки. Пустое значение означает: не рисовать пометку вовсе.
    disclaimer: str = ""

    def ensure_participants(self) -> None:
        if not self.participants:
            self.participants = [
                Participant(name="Участник 1", side=0),
                Participant(name="Участник 2", side=1),
            ]
        for idx, p in enumerate(self.participants):
            p.side = idx % 2

    def add_message(self, message: Message) -> Message:
        """Добавить сообщение с учётом лимита переписки.

        Лимит задаётся в настройках (``max_messages``) и не может
        превышать глобальный ``MAX_MESSAGES``.
        """
        limit = min(int(self.settings.max_messages or 0), MAX_MESSAGES) or MAX_MESSAGES
        if len(self.messages) >= limit:
            from bot.utils.errors import LimitExceededError

            raise LimitExceededError(
                f"Достигнут лимит: максимум {limit} сообщений в одной переписке.",
                retry_after=0,
            )
        self.messages.append(message)
        return message

    def find(self, message_id: str) -> Optional[Message]:
        for m in self.messages:
            if m.id == message_id:
                return m
        return None

    def index_of(self, message_id: str) -> int:
        for i, m in enumerate(self.messages):
            if m.id == message_id:
                return i
        return -1

    def move(self, index: int, delta: int) -> int:
        target = index + delta
        if 0 <= index < len(self.messages) and 0 <= target < len(self.messages):
            self.messages[index], self.messages[target] = (
                self.messages[target],
                self.messages[index],
            )
            return target
        return index

    def participants_label(self) -> str:
        names = [p.name for p in self.participants if p.name]
        if len(names) >= 2:
            return f"{names[0]} × {names[1]}"
        if names:
            return names[0]
        return "Без участников"

    def to_json(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def from_json(cls, data: Dict[str, Any] | str | None) -> "ChatConfig":
        if not data:
            return cls()
        if isinstance(data, str):
            import json

            try:
                data = json.loads(data)
            except (ValueError, TypeError):
                return cls()
        cfg = cls.model_validate(data)
        cfg.ensure_participants()
        return cfg


__all__ = [
    "MAX_MESSAGES",
    "MessageKind",
    "Reaction",
    "MediaItem",
    "Participant",
    "Message",
    "ChatSettings",
    "ChatConfig",
]
