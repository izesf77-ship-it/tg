"""Telegram Stars checkout, entitlement delivery, support, and refunds."""

from __future__ import annotations

import logging

from aiogram import F, Bot, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery
from sqlalchemy import func, select

from bot import screens
from bot.config import settings
from bot.keyboards import payments as PK
from bot.middleware import db_session, get_db_user
from bot.models import AICreditBalance, StarPayment, User
from bot.models.base import utcnow
from bot.services.payments_service import (
    PAYMENT_TERMS,
    PaymentsService,
    get_product,
    invoice_payload,
)
from bot.services.ai_service import ai_service
from bot.services.premium_service import premium_service
from bot.services.limit_service import LimitService
from bot.utils import callbacks as C

logger = logging.getLogger(__name__)
router = Router(name="payments")


def _support_text() -> str:
    admins = settings.admin_ids
    if not admins:
        return "Платёжная поддержка не настроена. Сообщите владельцу бота."
    links = "\n".join(
        f'• <a href="tg://user?id={admin_id}">Написать администратору</a>'
        for admin_id in admins
    )
    return (
        "💬 <b>Поддержка по оплате</b>\n\n"
        "Опишите проблему и приложите дату/сумму платежа. "
        "Поддержка Telegram не управляет покупками этого бота.\n\n"
        f"{links}"
    )


def _store_text(accepted: bool, credit_balance: int, user) -> str:
    if not accepted:
        return PAYMENT_TERMS
    lines = ["⭐️ <b>Магазин</b>", ""]
    if premium_service.is_premium(user):
        until = getattr(user, "premium_until", None)
        if until is None:
            lines.append("⭐️ Premium активен бессрочно.")
        else:
            lines.append(
                "⭐️ Premium активен до "
                f"<b>{until:%d.%m.%Y %H:%M} UTC</b>. "
                "Продление добавит ещё 30 дней."
            )
    else:
        lines.append(
            f"⭐️ <b>Premium · {premium_service.stars_price}⭐ / 30 дней</b>"
        )
        lines.append(
            "Больше лимитов, все стили и дополнительные возможности. "
            "Продление вручную, автосписания нет."
        )
    if not ai_service.enabled:
        lines.extend(
            [
                "",
                "AI-пакеты временно недоступны: сервис генерации не настроен.",
            ]
        )
    lines.extend(
        [
            "",
            f"✨ Куплено AI-генераций: <b>{credit_balance}</b>",
            "Пакеты не сгорают. Они расходуются после часового лимита "
            "обычной версии или Premium.",
            "",
            "Оплата цифровых товаров проходит только Telegram Stars.",
        ]
    )
    return "\n".join(lines)


async def show_store(target: Message | CallbackQuery) -> None:
    """Show terms before first purchase, otherwise show all products."""
    payments = PaymentsService(db_session())
    user_id = target.from_user.id
    accepted = await payments.has_accepted_terms(user_id)
    balance = await payments.credit_balance(user_id)
    user = get_db_user()
    if user is None:
        await screens.notify(target, "Не удалось загрузить аккаунт. Попробуйте ещё раз.")
        return
    if not accepted:
        await screens.show(target, PAYMENT_TERMS, PK.terms_keyboard())
        return
    await screens.show(
        target,
        _store_text(accepted, balance, user),
        PK.store_keyboard(
            can_buy_premium=not (
                user.is_premium and user.premium_until is None
            ),
            enabled=premium_service.enabled,
            ai_enabled=ai_service.enabled,
        ),
    )


@router.callback_query(F.data.startswith(C.S_PAY + ":"))
async def on_payment_action(callback: CallbackQuery) -> None:
    action = C.action(callback.data or "")
    payments = PaymentsService(db_session())

    if action == "noop":
        await screens.safe_answer(callback, "Оплата временно недоступна.")
        return
    if action == "terms":
        await screens.show(callback, PAYMENT_TERMS, PK.terms_keyboard())
        return
    if action == "support":
        await screens.safe_answer(callback)
        await callback.bot.send_message(
            callback.from_user.id,
            _support_text(),
            parse_mode=screens.PARSE_MODE,
            disable_web_page_preview=True,
        )
        return
    if action == "store":
        await show_store(callback)
        return
    if action == "accept_terms":
        await payments.accept_terms(callback.from_user.id)
        await show_store(callback)
        return
    if action != "buy":
        await screens.safe_answer(callback, "Неизвестное действие.", alert=True)
        return

    product = get_product(C.arg(callback.data or "", 0))
    if product is None:
        await screens.safe_answer(callback, "Товар не найден. Откройте магазин заново.", alert=True)
        return
    if not premium_service.enabled:
        await screens.safe_answer(callback, "Оплата временно недоступна.", alert=True)
        return
    if product.credits and not ai_service.enabled:
        await screens.safe_answer(
            callback,
            "AI-возможность временно отключена. Покупка пакетов появится после настройки сервиса.",
            alert=True,
        )
        return
    if not await payments.has_accepted_terms(callback.from_user.id):
        await screens.show(callback, PAYMENT_TERMS, PK.terms_keyboard())
        return
    user = get_db_user()
    if product.premium_days and user and user.is_premium and user.premium_until is None:
        await screens.safe_answer(callback, "У вас уже есть бессрочный Premium.", alert=True)
        return

    await screens.safe_answer(callback)
    try:
        await callback.bot.send_invoice(
            chat_id=callback.from_user.id,
            title=product.title,
            description=product.description,
            payload=invoice_payload(callback.from_user.id, product.id),
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=product.title, amount=product.stars)],
            start_parameter=f"buy_{product.id}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Не удалось создать Stars invoice (user=%s, product=%s)",
            callback.from_user.id,
            product.id,
            extra={"error_type": type(exc).__name__},
        )
        await callback.bot.send_message(
            callback.from_user.id,
            "Не удалось открыть оплату. Попробуйте позже или напишите /paysupport.",
        )


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery) -> None:
    """Validate amount, currency, buyer, and current terms before charging."""
    product_id = ""
    parts = (query.invoice_payload or "").split(":")
    if len(parts) == 3 and parts[0] == "stars":
        try:
            buyer_id = int(parts[1])
        except ValueError:
            buyer_id = -1
        product_id = parts[2]
    else:
        buyer_id = -1
    product = get_product(product_id)
    error = None
    if not premium_service.enabled:
        error = "Оплата временно недоступна. Попробуйте позже."
    elif buyer_id != query.from_user.id:
        error = "Этот счёт создан для другого пользователя."
    elif product is None:
        error = "Товар не найден. Откройте магазин и создайте новый счёт."
    elif product.credits and not ai_service.enabled:
        error = "AI-возможность временно отключена. Оплатить пакет сейчас нельзя."
    elif query.currency != "XTR" or query.total_amount != product.stars:
        error = "Сумма счёта изменилась. Создайте новый счёт в магазине."
    elif not await PaymentsService(db_session()).has_accepted_terms(query.from_user.id):
        error = "Перед оплатой откройте магазин и примите условия."
    elif product.premium_days:
        user = get_db_user()
        if user and user.is_premium and user.premium_until is None:
            error = "У вас уже есть бессрочный Premium."

    if error:
        await query.answer(ok=False, error_message=error)
        return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    payment = message.successful_payment
    if payment is None:
        return
    parts = (payment.invoice_payload or "").split(":")
    product = get_product(parts[2]) if len(parts) == 3 and parts[0] == "stars" else None
    service = PaymentsService(db_session())
    if product is None:
        logger.error("Получен успешный Stars платёж с неизвестным payload (user=%s)", message.from_user.id)
        try:
            refunded = await message.bot.refund_star_payment(
                user_id=message.from_user.id,
                telegram_payment_charge_id=payment.telegram_payment_charge_id,
            )
            if refunded:
                await message.answer(
                    "Не удалось определить покупку, поэтому платёж автоматически возвращён."
                )
            else:
                logger.error("Telegram отклонил возврат неизвестного платежа")
                await message.answer(
                    "Не удалось определить покупку или вернуть платёж. Напишите /paysupport."
                )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Не удалось вернуть платёж с неизвестным payload",
                extra={"error_type": type(exc).__name__},
            )
            await message.answer(
                "Платёж получен, но товар не удалось определить. Напишите /paysupport."
            )
        return

    try:
        granted = await service.record_payment(
            user_id=message.from_user.id,
            product=product,
            payload=payment.invoice_payload,
            currency=payment.currency,
            stars=payment.total_amount,
            telegram_charge_id=payment.telegram_payment_charge_id,
            provider_charge_id=payment.provider_payment_charge_id,
        )
    except ValueError:
        logger.exception("Некорректные данные успешного Stars платежа (user=%s)", message.from_user.id)
        try:
            refunded = await message.bot.refund_star_payment(
                user_id=message.from_user.id,
                telegram_payment_charge_id=payment.telegram_payment_charge_id,
            )
            if refunded:
                await message.answer("Данные платежа не совпали с товаром. Платёж возвращён.")
            else:
                logger.error("Telegram отклонил возврат некорректного платежа")
                await message.answer(
                    "Данные платежа не совпали с товаром и возврат не подтверждён. "
                    "Напишите /paysupport."
                )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Не удалось вернуть Stars платёж с некорректными данными",
                extra={"error_type": type(exc).__name__},
            )
            await message.answer(
                "Платёж получен, но покупку не удалось начислить. Напишите /paysupport."
            )
        return
    if not granted:
        await message.answer("Этот платёж уже был обработан.")
        return

    await db_session().commit()
    if product.premium_days:
        user = get_db_user()
        until = user.premium_until if user else None
        text = (
            "⭐️ <b>Premium активирован на 30 дней.</b>\n"
            f"Действует до {until:%d.%m.%Y %H:%M} UTC.\n"
            "Автопродления нет."
            if until
            else "⭐️ Premium активирован на 30 дней."
        )
    else:
        balance = await service.credit_balance(message.from_user.id)
        text = (
            f"✨ Начислено AI-генераций: <b>{product.credits}</b>.\n"
            f"Остаток: <b>{balance}</b>."
        )
    await message.answer(text, parse_mode=screens.PARSE_MODE)


@router.message(Command("terms"))
async def cmd_terms(message: Message) -> None:
    await message.answer(
        PAYMENT_TERMS,
        parse_mode=screens.PARSE_MODE,
        reply_markup=PK.terms_keyboard(),
    )


@router.message(Command("paysupport"))
@router.message(Command("support"))
async def cmd_payment_support(message: Message) -> None:
    await message.answer(
        _support_text(),
        parse_mode=screens.PARSE_MODE,
        disable_web_page_preview=True,
    )


@router.message(Command("refund"))
async def cmd_refund(message: Message, bot: Bot) -> None:
    """Admin-only refund by Telegram charge ID."""
    if not settings.is_admin(message.from_user.id):
        await message.answer("Команда доступна только администраторам.")
        return
    charge_id = (message.text or "").partition(" ")[2].strip()
    if not charge_id or len(charge_id) > 128:
        await message.answer("Использование: <code>/refund charge_id</code>", parse_mode="HTML")
        return

    session = db_session()
    service = PaymentsService(session)
    record = await service.get_payment_by_charge(charge_id)
    if record is None:
        await message.answer("Платёж не найден.")
        return
    if record.refunded_at is not None:
        await message.answer("Этот платёж уже возвращён.")
        return

    async with LimitService.rate_lock(record.user_id):
        record = await service.get_payment_by_charge(charge_id)
        if record is None or record.refunded_at is not None:
            await message.answer("Платёж уже обработан.")
            return
        credit = await session.get(AICreditBalance, record.user_id)
        if record.credits_granted and (
            record.credits_remaining != record.credits_granted
            or credit is None
            or credit.balance < record.credits_granted
        ):
            await message.answer(
                "Возврат пакета невозможен автоматически: часть AI-кредитов уже использована."
            )
            return
        try:
            refunded = await bot.refund_star_payment(
                user_id=record.user_id,
                telegram_payment_charge_id=record.telegram_charge_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Telegram Stars refund failed (payment_id=%s)",
                record.id,
                extra={"error_type": type(exc).__name__},
            )
            await message.answer("Telegram не подтвердил возврат. Повторите позже.")
            return
        if not refunded:
            await message.answer("Telegram не подтвердил возврат. Проверьте платёж.")
            return

        record.refunded_at = utcnow()
        if record.credits_granted and credit is not None:
            credit.balance -= record.credits_granted
            session.add(credit)
        if record.premium_until:
            user = await session.get(User, record.user_id)
            if user is not None:
                result = await session.execute(
                    select(StarPayment.premium_until).where(
                        StarPayment.user_id == record.user_id,
                        StarPayment.product_id == "premium30",
                        StarPayment.refunded_at.is_(None),
                        StarPayment.id != record.id,
                        StarPayment.premium_until > utcnow(),
                    )
                )
                ends = [item for item in result.scalars().all() if item is not None]
                user.premium_until = max(ends) if ends else None
                user.is_premium = bool(ends)
                session.add(user)
        session.add(record)
        await session.commit()
    await message.answer("✅ Возврат через Telegram Stars выполнен.")


@router.message(Command("payments"))
async def cmd_payments(message: Message) -> None:
    """Admin-only recent payment ledger, including charge IDs for refunds."""
    if not settings.is_admin(message.from_user.id):
        await message.answer("Команда доступна только администраторам.")
        return
    session = db_session()
    rows = await session.execute(
        select(StarPayment)
        .order_by(StarPayment.created_at.desc())
        .limit(20)
    )
    payments = list(rows.scalars().all())
    total_result = await session.execute(
        select(func.coalesce(func.sum(StarPayment.stars), 0)).where(
            StarPayment.refunded_at.is_(None)
        )
    )
    total_stars = int(total_result.scalar() or 0)
    lines = [f"💳 <b>Платежи</b> · не возвращено: {total_stars}⭐", ""]
    for item in payments:
        status = "возвращён" if item.refunded_at else "оплачен"
        lines.append(
            f"#{item.id} · user <code>{item.user_id}</code> · "
            f"{item.product_id} · {item.stars}⭐ · {status}\n"
            f"<code>{item.telegram_charge_id}</code>"
        )
    if not payments:
        lines.append("Платежей пока нет.")
    lines.append("\nВозврат: <code>/refund charge_id</code>")
    await message.answer("\n".join(lines), parse_mode=screens.PARSE_MODE)


__all__ = ["router", "show_store"]
