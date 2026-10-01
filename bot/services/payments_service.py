"""Telegram Stars product catalog and idempotent entitlement delivery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.models import (
    AICreditBalance,
    PaymentTermsAcceptance,
    StarPayment,
    User,
)
from bot.models.base import utcnow

TERMS_VERSION = "2026-10-01"
PAYMENT_TERMS = (
    "📜 <b>Условия цифровых покупок</b>\n\n"
    f"• Premium стоит {settings.premium_stars_price}⭐ и действует 30 дней. "
    "Автоматического продления нет. "
    "Повторная покупка вручную добавит 30 дней к текущему сроку.\n"
    "• AI-пакеты: 2 генерации за 15⭐, 5 за 30⭐ или 10 за 50⭐. "
    "Кредиты не сгорают и используются после часового бесплатного лимита "
    "(или лимита Premium).\n"
    "• Товар начисляется после подтверждённого Telegram платежа в Stars. "
    "Одно списание нельзя использовать повторно.\n"
    "• AI-сценарии являются вымышленным контентом. Работа AI зависит от "
    "доступности внешнего провайдера.\n"
    "• Вопросы по оплате и возвратам направляйте через /paysupport. "
    "Поддержка Telegram не управляет покупками этого бота.\n\n"
    "Нажимая «Принимаю», вы соглашаетесь с этими условиями."
)


@dataclass(frozen=True)
class Product:
    id: str
    title: str
    description: str
    stars: int
    credits: int = 0
    premium_days: int = 0


def products() -> tuple[Product, ...]:
    return (
        Product(
            "premium30",
            "Premium — 30 дней",
            "Premium-доступ на 30 дней, без автопродления",
            int(settings.premium_stars_price),
            premium_days=30,
        ),
        Product("ai2", "AI — 2 генерации", "Пакет из 2 AI-генераций", 15, credits=2),
        Product("ai5", "AI — 5 генераций", "Пакет из 5 AI-генераций", 30, credits=5),
        Product("ai10", "AI — 10 генераций", "Пакет из 10 AI-генераций", 50, credits=10),
    )


def get_product(product_id: str) -> Product | None:
    return next((item for item in products() if item.id == product_id), None)


def invoice_payload(user_id: int, product_id: str) -> str:
    return f"stars:{int(user_id)}:{product_id}"


class PaymentsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def has_accepted_terms(self, user_id: int) -> bool:
        acceptance = await self.session.get(PaymentTermsAcceptance, int(user_id))
        return bool(acceptance and acceptance.version == TERMS_VERSION)

    async def accept_terms(self, user_id: int) -> None:
        statement = sqlite_insert(PaymentTermsAcceptance).values(
            user_id=int(user_id),
            version=TERMS_VERSION,
            accepted_at=utcnow(),
        )
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[PaymentTermsAcceptance.user_id],
                set_={"version": TERMS_VERSION, "accepted_at": utcnow()},
            )
        )
        await self.session.commit()

    async def credit_balance(self, user_id: int) -> int:
        row = await self.session.get(AICreditBalance, int(user_id))
        return max(0, int(row.balance)) if row else 0

    async def record_payment(
        self,
        *,
        user_id: int,
        product: Product,
        payload: str,
        currency: str,
        stars: int,
        telegram_charge_id: str,
        provider_charge_id: str | None,
    ) -> bool:
        """Record a successful payment once and grant its entitlement."""
        if (
            currency != "XTR"
            or stars != product.stars
            or payload != invoice_payload(user_id, product.id)
        ):
            raise ValueError("Telegram Stars payment details do not match the product")

        existing_id = await self.session.scalar(
            select(StarPayment.id).where(
                StarPayment.telegram_charge_id == telegram_charge_id
            )
        )
        if existing_id is not None:
            return False

        now = utcnow()
        user = None
        if product.premium_days:
            user = await self.session.get(User, int(user_id))
            if user is None:
                raise ValueError("Payment user does not exist")
            if user.is_premium and user.premium_until is None:
                raise ValueError("A permanent Premium account cannot be extended")
        statement = sqlite_insert(StarPayment).values(
            user_id=int(user_id),
            product_id=product.id,
            stars=stars,
            credits_granted=product.credits,
            credits_remaining=product.credits,
            invoice_payload=payload,
            telegram_charge_id=telegram_charge_id,
            provider_charge_id=provider_charge_id,
            premium_until=None,
            created_at=now,
            refunded_at=None,
        )
        inserted = await self.session.execute(
            statement.on_conflict_do_nothing(
                index_elements=[StarPayment.telegram_charge_id]
            )
        )
        if inserted.rowcount != 1:
            return False

        if product.premium_days:
            assert user is not None
            start = user.premium_until if user.premium_until and user.premium_until > now else now
            end = start + timedelta(days=product.premium_days)
            user.is_premium = True
            user.premium_until = end
            await self.session.execute(
                update(StarPayment)
                .where(StarPayment.telegram_charge_id == telegram_charge_id)
                .values(premium_until=end)
            )
            self.session.add(user)
        elif product.credits:
            credit_insert = sqlite_insert(AICreditBalance).values(
                user_id=int(user_id),
                balance=product.credits,
                updated_at=now,
            )
            await self.session.execute(
                credit_insert.on_conflict_do_update(
                    index_elements=[AICreditBalance.user_id],
                    set_={
                        "balance": AICreditBalance.balance + product.credits,
                        "updated_at": now,
                    },
                )
            )

        await self.session.flush()
        return True

    async def get_payment_by_charge(self, charge_id: str) -> StarPayment | None:
        result = await self.session.execute(
            select(StarPayment).where(StarPayment.telegram_charge_id == charge_id)
        )
        return result.scalar_one_or_none()


__all__ = [
    "PAYMENT_TERMS",
    "TERMS_VERSION",
    "PaymentsService",
    "Product",
    "get_product",
    "invoice_payload",
    "products",
]
