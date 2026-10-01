"""Persistent payment records and entitlements for Telegram Stars."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from bot.models.base import Base, UTCDateTime, utcnow


class StarPayment(Base):
    __tablename__ = "star_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, index=True
    )
    product_id: Mapped[str] = mapped_column(String(32), nullable=False)
    stars: Mapped[int] = mapped_column(Integer, nullable=False)
    credits_granted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    credits_remaining: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    invoice_payload: Mapped[str] = mapped_column(String(128), nullable=False)
    telegram_charge_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False
    )
    provider_charge_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    premium_until: Mapped[Optional["UTCDateTime"]] = mapped_column(
        UTCDateTime, nullable=True
    )
    created_at: Mapped["UTCDateTime"] = mapped_column(
        UTCDateTime, default=utcnow, nullable=False
    )
    refunded_at: Mapped[Optional["UTCDateTime"]] = mapped_column(
        UTCDateTime, nullable=True
    )


class AICreditBalance(Base):
    __tablename__ = "ai_credit_balances"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped["UTCDateTime"] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class PaymentTermsAcceptance(Base):
    __tablename__ = "payment_terms_acceptances"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    accepted_at: Mapped["UTCDateTime"] = mapped_column(
        UTCDateTime, default=utcnow, nullable=False
    )


__all__ = ["AICreditBalance", "PaymentTermsAcceptance", "StarPayment"]
