"""Админ-панель: статистика, пользователи, рассылка, лимиты."""

from __future__ import annotations

from bot.middleware import get_services
from bot.services.limit_service import ensure_loaded
import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import screens
from bot.config import settings
from bot.database.engine import session_scope
from bot.database.repositories import BroadcastRepository, StatsRepository, UserRepository
from bot.keyboards import admin as AK
from bot.keyboards import common as KB
from bot.keyboards import texts as T
from bot.states import Flow
from bot.utils import callbacks as C
from bot.utils import text_utils as TX

logger = logging.getLogger(__name__)

router = Router(name="admin")

USERS_PAGE = 8
BROADCAST_DELAY = 0.05  # пауза между сообщениями, чтобы не словить лимит Telegram


def is_admin(user_id: int) -> bool:
    return settings.is_admin(int(user_id))


async def _guard(target) -> bool:
    """Проверка прав: молча отклоняет не-админов."""
    if is_admin(target.from_user.id):
        return True
    logger.info("Попытка доступа к админке: user=%s", target.from_user.id)
    await screens.notify(target, "🚫 Доступно только администраторам.")
    return False


async def send_stats(target) -> None:
    """Собрать и показать статистику."""
    async with session_scope() as session:
        stats = await StatsRepository(session).collect()

    text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 Пользователей: <b>{stats.users}</b>\n"
        f"🆕 Новых сегодня: <b>{stats.users_today}</b>\n"
        f"⚡ Активных за 24 ч: <b>{stats.active_24h}</b>\n"
        f"📅 Активных за 7 дней: <b>{stats.active_7d}</b>\n\n"
        f"📂 Переписок создано: <b>{stats.chats}</b>\n"
        f"📝 Черновиков: <b>{stats.drafts}</b>\n"
        f"🖼 Изображений сгенерировано: <b>{stats.images}</b>\n"
        f"🖼 Изображений сегодня: <b>{stats.images_today}</b>\n"
        f"✨ AI-генераций: <b>{stats.ai}</b>\n"
        f"✨ AI-генераций сегодня: <b>{stats.ai_today}</b>\n"
        f"⚡ Всего действий: <b>{stats.actions}</b>"
    )
    if stats.styles:
        parts = ", ".join(f"{k}: {v}" for k, v in stats.styles.items())
        text += f"\n\n🎨 Стили: {TX.esc(parts)}"
    if stats.top_users:
        top = "\n".join(f"  {uid} — {count}" for uid, count in stats.top_users[:5])
        text += f"\n\n🏆 Топ по генерациям:\n{top}"

    if isinstance(target, Message):
        await target.answer(text, parse_mode=screens.PARSE_MODE, reply_markup=AK.admin_menu())
    else:
        await screens.show(target, text, AK.admin_menu())


@router.message(Command("admin"))
@router.message(Command("stats"))
async def cmd_admin(message: Message) -> None:
    """Точка входа в админ-панель."""
    if not await _guard(message):
        return
    if (message.text or "").startswith("/stats"):
        await send_stats(message)
        return
    await message.answer(
        "🛠 <b>Админ-панель</b>\n\nСтатистика, пользователи, рассылка и лимиты.",
        parse_mode=screens.PARSE_MODE,
        reply_markup=AK.admin_menu(),
    )


def _default_limits() -> dict:
    return {
        "limit_image_per_hour": settings.limit_image_per_hour,
        "limit_ai_per_hour": settings.limit_ai_per_hour,
        "limit_image_per_hour_premium": settings.limit_image_per_hour_premium,
        "limit_ai_per_hour_premium": settings.limit_ai_per_hour_premium,
        "limit_actions_per_minute": settings.limit_actions_per_minute,
        "max_messages": settings.max_messages,
        "max_chats": settings.max_chats,
    }


def _current_limits(limits) -> dict:
    """Значения лимитов с учётом переопределений из БД.

    Раньше тут было ``limits.overrides() or _default_limits()``: если
    переопределений не было, показывались дефолты, а стоило изменить один
    параметр — список показывал только его, и остальные выглядели
    сброшенными. Теперь всегда показываются все семь параметров.
    """
    values = _default_limits()
    values.update(limits.overrides())
    return values


@router.callback_query(F.data.startswith(C.S_ADMIN + ":"))
async def on_admin(callback: CallbackQuery, state: FSMContext) -> None:
    """Действия админ-панели."""
    if not await _guard(callback):
        return
    action = C.action(callback.data)

    if action == "noop":
        await screens.safe_answer(callback)
        return
    if action == "home":
        await screens.show(
            callback, "🛠 <b>Админ-панель</b>\n\nУправление ботом.", AK.admin_menu()
        )
        return
    if action == "stats":
        await send_stats(callback)
        return
    if action == "users":
        await show_users(callback, 0)
        return

    if action == "broadcast":
        await state.set_state(Flow.broadcast_text)
        await screens.ask(
            callback,
f"📢 <b>Рассылка</b>\n\n{T.field_prompt('broadcast')}\n\n"
            "Рассылка начнётся только после подтверждения.",
            reply_markup=KB.input_menu("Введите текст рассылки…")
        )
        return

    if action == "limits":
        limits = get_services()["limits"]
        await ensure_loaded()
        current = _current_limits(limits)
        await screens.show(
            callback,
            "⚙️ <b>Лимиты</b>\n\nВыберите параметр для изменения.",
            AK.limits_menu(current),
        )
        return

    if action == "limits_reset":
        limits = get_services()["limits"]
        removed = await limits.reset_overrides()
        logger.info("Админ %s сбросил лимиты (%s)", callback.from_user.id, removed)
        await screens.show(
            callback,
            "♻️ Лимиты сброшены к значениям из .env",
            AK.limits_menu(_default_limits()),
        )
        return

    if action == "limit":
        key = C.arg(callback.data, 0)
        await state.set_state(Flow.admin_limit)
        await state.update_data(limit_key=key)
        await screens.ask(
            callback,
f"✏️ <b>Новое значение</b>\n\nПараметр: <code>{TX.esc(key)}</code>\n\n"
            "Введите целое число (0 — без лимита).",
            reply_markup=KB.input_menu("Например: 30")
        )
        return

    if action == "send":
        await start_broadcast(callback, C.arg_int(callback.data, 0, -1))
        return
    if action == "cancel_send":
        await screens.show(callback, "❌ Рассылка отменена.", AK.admin_menu())
        return

    await screens.safe_answer(callback, "Неизвестное действие.", alert=True)


# --- Пользователи --------------------------------------------------------
async def show_users(target, page: int = 0) -> None:
    """Список пользователей с пагинацией."""
    async with session_scope() as session:
        repo = UserRepository(session)
        total = await repo.count()
        users = await repo.page(page * USERS_PAGE, USERS_PAGE)
    pages = max(1, (total + USERS_PAGE - 1) // USERS_PAGE)
    page = min(page, pages - 1)

    lines = [f"👥 <b>Пользователи</b> ({total})", ""]
    for user in users:
        premium = " ⭐️" if user.is_premium else ""
        lines.append(
            f"<code>{user.id}</code> {TX.esc(user.display_name)}{premium}\n"
            f"   🖼 {user.total_images} · 📂 {user.total_chats} · ✨ {user.total_ai}"
        )
    lines.append(f"\nСтраница {page + 1} из {pages}")

    if isinstance(target, Message):
        await target.answer(
            "\n".join(lines),
            parse_mode=screens.PARSE_MODE,
            reply_markup=AK.users_page(page, pages),
        )
    else:
        await screens.show(target, "\n".join(lines), AK.users_page(page, pages))


@router.message(Command("users"))
async def cmd_users(message: Message) -> None:
    if not await _guard(message):
        return
    await show_users(message, 0)


# --- Ввод лимитов --------------------------------------------------------
@router.message(Flow.admin_limit, F.text)
async def on_limit_value(message: Message, state: FSMContext) -> None:
    """Новое значение лимита от администратора."""
    if not await _guard(message):
        return
    data = await state.get_data()
    key = str(data.get("limit_key", ""))
    raw = (message.text or "").strip()
    try:
        value = int(raw)
        if value < 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите целое неотрицательное число. Например: 30")
        return

    limits = get_services()["limits"]
    await limits.set_override(key, value)
    logger.info("Админ %s изменил лимит %s=%s", message.from_user.id, key, value)
    await state.clear()
    await message.answer(
        f"✅ Лимит <code>{TX.esc(key)}</code> = <b>{value}</b>\n\n"
        "Остальные лимиты остались без изменений.",
        parse_mode=screens.PARSE_MODE,
        reply_markup=AK.limits_menu(_current_limits(limits)),
    )


# --- Рассылка ------------------------------------------------------------
@router.message(Flow.broadcast_text, F.text)
async def on_broadcast_text(message: Message, state: FSMContext) -> None:
    """Текст рассылки — показываем подтверждение, НЕ отправляем сразу."""
    if not await _guard(message):
        return
    text = TX.clean(message.text or "")
    if not text:
        await message.answer("Текст рассылки не может быть пустым.")
        return
    if len(text) > 3500:
        await message.answer("Текст слишком длинный (максимум 3500 символов).")
        return

    async with session_scope() as session:
        repo = BroadcastRepository(session)
        item = await repo.create(message.from_user.id, text)
        total = await UserRepository(session).count()
        broadcast_id = item.id

    logger.info("Админ %s подготовил рассылку #%s (%s символов)",
                message.from_user.id, broadcast_id, len(text))
    await state.clear()
    await message.answer(
        "📢 <b>Подтвердите рассылку</b>\n\n"
        f"👥 Получателей: <b>{total}</b>\n"
        f"📝 Символов: <b>{len(text)}</b>\n\n"
        "<i>Текст рассылки:</i>\n"
        f"{TX.esc(text[:600])}\n\n"
        "⚠️ Отправка необратима.",
        parse_mode=screens.PARSE_MODE,
        reply_markup=AK.broadcast_confirm(broadcast_id, total),
    )


async def start_broadcast(target, broadcast_id: int) -> None:
    """Отправить рассылку всем пользователям."""
    if not await _guard(target):
        return
    bot: Bot = target.message.bot if target.message else None
    if bot is None or broadcast_id < 0:
        await screens.safe_answer(target, "Рассылка не найдена.", alert=True)
        return

    async with session_scope() as session:
        repo = BroadcastRepository(session)
        item = await repo.get(broadcast_id)
        if item is None:
            await screens.safe_answer(target, "Рассылка не найдена.", alert=True)
            return
        text = item.text
        await repo.update(item, status="sending")
        users = await UserRepository(session).iter_all()

    logger.info("Рассылка #%s: %s получателей", broadcast_id, len(users))
    progress = await target.message.answer(
        f"📤 <b>Рассылка началась</b>\n\nПолучателей: {len(users)}",
        parse_mode=screens.PARSE_MODE,
    )

    sent = failed = 0
    for index, user in enumerate(users, 1):
        try:
            await bot.send_message(user.id, text)
            sent += 1
        except Exception as exc:  # noqa: BLE001 - заблокированные и т.п.
            failed += 1
            logger.debug("Рассылка: user=%s ошибка %s", user.id, type(exc).__name__)
        if index % 10 == 0:
            try:
                await progress.edit_text(
                    f"📤 <b>Рассылка</b>\n\nОтправлено: {sent} из {len(users)}",
                    parse_mode=screens.PARSE_MODE,
                )
            except Exception:  # noqa: BLE001
                pass
        await asyncio.sleep(BROADCAST_DELAY)

    async with session_scope() as session:
        repo = BroadcastRepository(session)
        item = await repo.get(broadcast_id)
        if item is not None:
            await repo.finish(item, sent, failed)

    logger.info("Рассылка #%s завершена: отправлено=%s, ошибок=%s",
                broadcast_id, sent, failed)
    try:
        await progress.edit_text(
            f"✅ <b>Рассылка завершена</b>\n\n"
            f"Отправлено: <b>{sent}</b>\n"
            f"Не доставлено: <b>{failed}</b>",
            parse_mode=screens.PARSE_MODE,
            reply_markup=AK.admin_menu(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Не удалось обновить статус рассылки: %s", exc)


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext) -> None:
    """Сразу запрашивает текст рассылки (для админов)."""
    if not await _guard(message):
        return
    await state.set_state(Flow.broadcast_text)
    await message.answer(
        f"📢 <b>Рассылка</b>\n\n{T.field_prompt('broadcast')}\n\n"
        "После ввода будет показано подтверждение.",
        parse_mode=screens.PARSE_MODE,
        reply_markup=KB.input_menu("Введите текст рассылки…"),
    )


__all__ = [
    "router", "is_admin", "cmd_admin", "send_stats", "show_users",
    "on_admin", "on_broadcast_text", "on_limit_value", "cmd_users",
    "cmd_broadcast", "start_broadcast",
]