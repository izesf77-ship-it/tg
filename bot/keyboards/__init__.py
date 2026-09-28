"""Клавиатуры интерфейса бота."""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from bot.keyboards import admin, common, create, editor, menus, my_chats
from bot.keyboards.common import (
    back_button,
    cancel_menu,
    hide_keyboard,
    input_menu,
    main_menu,
    main_menu_inline,
)
from bot.keyboards.create import participants_menu, style_menu, templates_menu
from bot.keyboards.editor import done_keyboard, editor_keyboard, preview_keyboard
from bot.keyboards.menus import ai_menu, chats_list, global_settings_menu

__all__ = [
    "InlineKeyboardButton",
    "InlineKeyboardMarkup",
    "KeyboardButton",
    "ReplyKeyboardMarkup",
    "ReplyKeyboardRemove",
    "InlineKeyboardBuilder",
    "ReplyKeyboardBuilder",
    "admin",
    "common",
    "create",
    "editor",
    "menus",
    "my_chats",
    "main_menu",
    "main_menu_inline",
    "cancel_menu",
    "input_menu",
    "back_button",
    "hide_keyboard",
    "style_menu",
    "participants_menu",
    "templates_menu",
    "editor_keyboard",
    "preview_keyboard",
    "done_keyboard",
    "chats_list",
    "ai_menu",
    "global_settings_menu",
]

