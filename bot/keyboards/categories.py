from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.constants import (
    CANCEL,
    CATEGORY_ADD,
    CATEGORY_DELETE,
    CATEGORY_RENAME_ICON,
    DELETE_NO,
    DELETE_YES,
)
from bot.services.categories import MAX_CUSTOM_CATEGORIES


class CategoryAction(CallbackData, prefix="cm"):
    """Shaxsiy kategoriyalar. category_id ga ishonilmaydi — egasi bazada tekshiriladi."""

    action: str  # add | ren | del | delok | cancel
    category_id: int = 0


def manage_keyboard(custom: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    """custom: (id, yorliq). Har biriga qator: [✏️ nom] [🗑 O'chirish]. Limitgacha — qo'shish."""

    def button(text: str, action: str, category_id: int) -> InlineKeyboardButton:
        data = CategoryAction(action=action, category_id=category_id)
        return InlineKeyboardButton(text=text, callback_data=data.pack())

    b = InlineKeyboardBuilder()
    if len(custom) < MAX_CUSTOM_CATEGORIES:
        b.row(button(CATEGORY_ADD, "add", 0))
    for category_id, label in custom:
        b.row(
            button(f"{CATEGORY_RENAME_ICON} {label}", "ren", category_id),
            button(CATEGORY_DELETE, "del", category_id),
        )
    return b.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=CANCEL, callback_data=CategoryAction(action="cancel"))
    return b.as_markup()


def delete_confirm_keyboard(category_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(
        text=DELETE_YES,
        callback_data=CategoryAction(action="delok", category_id=category_id),
    )
    b.button(text=DELETE_NO, callback_data=CategoryAction(action="cancel"))
    return b.as_markup()
