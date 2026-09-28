"""Сервис работы с переписками: создание, автосохранение, дублирование."""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.repositories import ChatRepository
from bot.models import Chat
from bot.schemas import ChatConfig, Message, Participant
from bot.utils.errors import ChatNotFoundError, MessageNotFoundError, NoMessagesError

logger = logging.getLogger(__name__)


class ChatService:
    """Все операции над перепиской, которые нужны хендлерам."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ChatRepository(session)

    # --- Создание ---------------------------------------------------
    async def create(
        self,
        user_id: int,
        style: str = "telegram",
        template: str = "",
        is_draft: bool = True,
    ) -> Tuple[Chat, ChatConfig]:
        config = ChatConfig(title="Переписка", style=style, template=template)
        config.ensure_participants()
        chat = await self.repo.create(user_id, config, is_draft=is_draft)
        logger.info("Создана переписка #%s (style=%s, user=%s)", chat.id, style, user_id)
        return chat, config

    async def get_chat(self, user_id: int, chat_id: int) -> Optional[Chat]:
        return await self.repo.get_for_user(user_id, chat_id)

    async def require_chat(self, user_id: int, chat_id: int) -> Chat:
        chat = await self.get_chat(user_id, chat_id)
        if chat is None:
            raise ChatNotFoundError()
        return chat

    async def get_config(self, user_id: int, chat_id: int) -> ChatConfig:
        chat = await self.require_chat(user_id, chat_id)
        return await self.repo.load_config(chat)

    async def save(self, user_id: int, chat_id: int, config: ChatConfig) -> Chat:
        """Сохранить состояние (вызывается после каждого действия)."""
        chat = await self.require_chat(user_id, chat_id)
        return await self.repo.save(chat, config)

    # --- Черновики ---------------------------------------------------
    async def get_draft(self, user_id: int) -> Optional[Chat]:
        return await self.repo.get_draft(user_id)

    async def draft_config(self, user_id: int) -> Optional[ChatConfig]:
        chat = await self.get_draft(user_id)
        return await self.repo.load_config(chat) if chat else None

    async def clear_drafts(self, user_id: int) -> int:
        removed = await self.repo.clear_drafts(user_id)
        if removed:
            logger.info("Удалено черновиков: %s (user=%s)", removed, user_id)
        return removed

    async def count_saved(self, user_id: int) -> int:
        return await self.repo.count_for_user(user_id, only_saved=True)

    # --- Финализация -------------------------------------------------
    async def finish(self, user_id: int, chat_id: int, config: ChatConfig) -> Chat:
        chat = await self.require_chat(user_id, chat_id)
        await self.repo.save(chat, config)
        saved = await self.repo.finish_draft(chat)
        logger.info("Переписка #%s сохранена", chat_id)
        return saved

    async def duplicate(self, user_id: int, chat_id: int) -> Chat:
        chat = await self.require_chat(user_id, chat_id)
        copy = await self.repo.duplicate(chat)
        logger.info("Переписка #%s -> копия #%s", chat_id, copy.id)
        return copy

    async def delete(self, user_id: int, chat_id: int) -> None:
        chat = await self.require_chat(user_id, chat_id)
        await self.repo.delete(chat)
        logger.info("Переписка #%s удалена (user=%s)", chat_id, user_id)

    async def list_saved(
        self, user_id: int, limit: int = 10, offset: int = 0
    ) -> List[Chat]:
        return await self.repo.list_for_user(
            user_id, only_saved=True, limit=limit, offset=offset
        )

    async def count_render(self, chat_id: int) -> None:
        await self.repo.increment_renders(chat_id)

    # --- Операции над сообщениями ------------------------------------
    def add_message(self, config: ChatConfig, message: Message) -> Message:
        return config.add_message(message)

    @staticmethod
    def require_message(config: ChatConfig, message_id: str) -> Message:
        message = config.find(message_id)
        if message is None:
            raise MessageNotFoundError()
        return message

    @staticmethod
    def require_content(config: ChatConfig) -> None:
        if not config.messages:
            raise NoMessagesError()

    @staticmethod
    def delete_message(config: ChatConfig, message_id: str) -> None:
        index = config.index_of(message_id)
        if index < 0:
            raise MessageNotFoundError()
        config.messages.pop(index)
        for msg in config.messages:
            if msg.reply_to == message_id:
                msg.reply_to = None

    @staticmethod
    def move_message(config: ChatConfig, message_id: str, delta: int) -> int:
        """Сдвинуть сообщение на ``delta`` позиций; вернуть новый индекс."""
        index = config.index_of(message_id)
        if index < 0:
            raise MessageNotFoundError()
        return config.move(index, delta)

    # --- Участники -----------------------------------------------------
    @staticmethod
    def participant(config: ChatConfig, index: int) -> Optional[Participant]:
        if 0 <= index < len(config.participants):
            return config.participants[index]
        return None

    @staticmethod
    def ensure_two(config: ChatConfig) -> ChatConfig:
        config.ensure_participants()
        return config

    def author_name(self, config: ChatConfig, message: Message) -> str:
        part = self.participant(config, message.author_index)
        return part.short_name if part else "Участник"


chat_service: Optional[ChatService] = None


def bind(session: AsyncSession) -> ChatService:
    global chat_service
    chat_service = ChatService(session)
    return chat_service


__all__ = ["ChatService", "bind"]