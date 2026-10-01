"""Telegram Stars shop and payment terms keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.payments_service import products
from bot.utils import callbacks as C


def terms_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="✅ Принимаю условия",
            callback_data=C.cb(C.S_PAY, "accept_terms"),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=C.cb(C.S_PAY, "store"),
        )
    )
    return kb.as_markup()


def store_keyboard(
    *, can_buy_premium: bool, enabled: bool = True, ai_enabled: bool = True
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if enabled:
        if can_buy_premium:
            kb.row(
                InlineKeyboardButton(
                    text=f"⭐ Premium · {products()[0].stars}⭐ / 30 дней",
                    callback_data=C.cb(C.S_PAY, "buy", "premium30"),
                )
            )
        for product in products():
            if product.credits and ai_enabled:
                kb.row(
                    InlineKeyboardButton(
                        text=f"✨ {product.credits} AI · {product.stars}⭐",
                        callback_data=C.cb(C.S_PAY, "buy", product.id),
                    )
                )
    else:
        kb.row(
            InlineKeyboardButton(
                text="Оплата временно недоступна",
                callback_data=C.cb(C.S_PAY, "noop"),
            )
        )
    kb.row(
        InlineKeyboardButton(
            text="📜 Условия оплаты",
            callback_data=C.cb(C.S_PAY, "terms"),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="💬 Поддержка по оплате",
            callback_data=C.cb(C.S_PAY, "support"),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="⬅️ В меню",
            callback_data=C.cb(C.S_MENU, "home"),
        )
    )
    return kb.as_markup()


def ai_packs_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for product in products():
        if product.credits:
            kb.row(
                InlineKeyboardButton(
                    text=f"✨ {product.credits} AI · {product.stars}⭐",
                    callback_data=C.cb(C.S_PAY, "buy", product.id),
                )
            )
    kb.row(
        InlineKeyboardButton(
            text="⭐ Все предложения",
            callback_data=C.cb(C.S_PAY, "store"),
        )
    )
    return kb.as_markup()
__all__ = ["ai_packs_keyboard", "store_keyboard", "terms_keyboard"]
