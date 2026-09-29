"""Репозиторий переписок."""

from __future__ import annotations

import copy
from typing import Any, List, Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Chat
from bot.schemas import ChatConfig


class ChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user_id: int, config: ChatConfig, is_draft: bool = True) -> Chat:
        chat = Chat(
            user_id=int(user_id),
            title=config.title[:128] or "Переписка",
            style=config.style,
            config=config.to_json(),
            message_count=len(config.messages),
            is_draft=is_draft,
            template=config.template,
        )
        self.session.add(chat)
        await self.session.flush()
        return chat

    async def get(self, chat_id: int) -> Optional[Chat]:
        return await self.session.get(Chat, int(chat_id))

    async def get_for_user(self, user_id: int, chat_id: int) -> Optional[Chat]:
        result = await self.session.execute(
            select(Chat).where(Chat.id == int(chat_id), Chat.user_id == int(user_id))
        )
        return result.scalar_one_or_none()

    async def save(self, chat: Chat, config: ChatConfig) -> Chat:
        chat.title = config.title[:128] or "Переписка"
        chat.style = config.style
        chat.config = config.to_json()
        chat.message_count = len(config.messages)
        chat.template = config.template
        self.session.add(chat)
        await self.session.flush()
        return chat

    async def load_config(self, chat: Chat) -> ChatConfig:
        data: Any = chat.config
        return ChatConfig.from_json(data)

    def load_config_sync(self, chat: Chat) -> ChatConfig:
        """Синхронная загрузка конфига уже загруженной модели.

        Нужна там, где объект ``Chat`` уже есть в сессии, а ждать
        дополнительный SELECT не требуется (например, проверка черновика
        на наличие заполненных участников при входе в бота).
        """
        return ChatConfig.from_json(chat.config)

    async def duplicate(self, chat: Chat) -> Chat:
        data = copy.deepcopy(dict(chat.config or {}))
        new_config = ChatConfig.from_json(data)
        new_config.title = f"{chat.title} (копия)"[:128]
        return await self.create(chat.user_id, new_config, is_draft=False)

    async def delete(self, chat: Chat) -> None:
        await self.session.delete(chat)
        await self.session.flush()

    async def list_for_user(
        self, user_id: int, only_saved: bool = False, limit: int = 50, offset: int = 0
    ) -> List[Chat]:
        stmt = select(Chat).where(Chat.user_id == int(user_id))
        if only_saved:
            stmt = stmt.where(Chat.is_draft.is_(False))
        stmt = stmt.order_by(Chat.updated_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_user(self, user_id: int, only_saved: bool = False) -> int:
        stmt = select(func.count(Chat.id)).where(Chat.user_id == int(user_id))
        if only_saved:
            stmt = stmt.where(Chat.is_draft.is_(False))
        result = await self.session.execute(stmt)
        return int(result.scalar() or 0)

    async def get_draft(self, user_id: int) -> Optional[Chat]:
        result = await self.session.execute(
            select(Chat)
            .where(Chat.user_id == int(user_id), Chat.is_draft.is_(True))
            .order_by(Chat.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def count_drafts(self, user_id: int) -> int:
        result = await self.session.execute(
            select(func.count(Chat.id)).where(
                Chat.user_id == int(user_id), Chat.is_draft.is_(True)
            )
        )
        return int(result.scalar() or 0)

    async def clear_drafts(self, user_id: int) -> int:
        result = await self.session.execute(select(Chat).where(
            Chat.user_id == int(user_id), Chat.is_draft.is_(True)
        ))
        drafts = list(result.scalars().all())
        for draft in drafts:
            await self.session.delete(draft)
        await self.session.flush()
        return len(drafts)

    async def finish_draft(self, chat: Chat) -> Chat:
        chat.is_draft = False
        self.session.add(chat)
        await self.session.flush()
        return chat

    async def increment_renders(self, chat_id: int) -> None:
        await self.session.execute(
            update(Chat).where(Chat.id == int(chat_id)).values(renders_count=Chat.renders_count + 1)
        )
        await self.session.flush()

    async def count(self) -> int:
        result = await self.session.execute(select(func.count(Chat.id)))
        return int(result.scalar() or 0)

    async def count_drafts_global(self) -> int:
        result = await self.session.execute(
            select(func.count(Chat.id)).where(Chat.is_draft.is_(True))
        )
        return int(result.scalar() or 0)


__all__ = ["ChatRepository"]
