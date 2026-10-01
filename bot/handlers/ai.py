"""AI-генерация сценария переписки через OpenRouter."""

from __future__ import annotations

from bot.middleware import get_services, is_premium
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot import screens
from bot.keyboards import common as KB
from bot.keyboards import texts as T
from bot.services.ai_service import ai_service
from bot.states import Flow
from bot.utils import text_utils as TX
from bot.utils.errors import AIError, AIUnavailableError

logger = logging.getLogger(__name__)

router = Router(name="ai")

MAX_PROMPT = 1500


@router.message(Flow.ai_prompt, F.text)
async def on_ai_prompt(message: Message, state: FSMContext) -> None:
    """Обработать описание сценария и создать переписку по нему."""
    prompt = TX.clean(message.text or "")
    if not prompt:
        await message.answer("Опишите сценарий подробнее.")
        return
    if len(prompt) > MAX_PROMPT:
        prompt = prompt[:MAX_PROMPT]

    limits = get_services()["limits"]
    users = get_services()["user"]
    chats = get_services()["chats"]
    # user может быть None, если БД была занята при регистрации (тогда
    # middleware откатил сессию). Раньше здесь стояло user.is_premium —
    # и вместо ответа на лимит пользователь получал AttributeError.
    premium = is_premium()

    if not ai_service.enabled:
        await message.answer(T.HELP_AI_DISABLED, parse_mode=screens.PARSE_MODE)
        await state.clear()
        return

    if await chats.count_all(message.from_user.id) >= limits.max_chats(premium):
        await message.answer(
            "Достигнут лимит переписок. Удалите ненужные в разделе «Мои переписки»."
        )
        return

    check = await limits.reserve_ai(message.from_user.id, premium)
    if not check:
        await message.answer(check.text or "Лимит AI-запросов исчерпан.")
        return

    status = await message.answer(
        "⏳ <b>AI придумывает сценарий…</b>\n\nЭто может занять до 45 секунд.",
        parse_mode=screens.PARSE_MODE,
    )

    try:
        config = await ai_service.generate(prompt)
    except (AIUnavailableError, AIError) as exc:
        await _edit(status, f"⚠️ {exc.user_message}")
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("Непредвиденная ошибка AI")
        await _edit(status, "⚠️ Не удалось получить сценарий. Попробуйте ещё раз.")
        return

    chat, _ = await chats.create(
        message.from_user.id, style="telegram", template="ai", is_draft=True
    )
    config.title = TX.clamp(config.title, 48)
    await chats.save(message.from_user.id, chat.id, config)
    await users.count_chat(message.from_user.id)
    await users.count_ai(message.from_user.id)

    await _edit(status, "")
    await state.set_state(Flow.editor)
    await state.update_data(chat_id=chat.id, page=0)

    from bot.handlers.editor import show_editor

    await show_editor(
        message, config, chat.id, state, 0,
        header="✨ <b>AI-сценарий создан</b>\n\n" + T.ai_result(config),
    )


async def _edit(message: Message, text: str) -> None:
    try:
        if text:
            await message.edit_text(text, parse_mode=screens.PARSE_MODE)
        else:
            await message.delete()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Не удалось обновить статус AI: %s", exc)


__all__ = ["router", "on_ai_prompt"]
