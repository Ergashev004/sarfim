from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.constants import CANCEL, CATEGORY_ADD, DELETE_NO, DELETE_YES
from bot.services.categories import MAX_CUSTOM_CATEGORIES


class CategoryAction(CallbackData, prefix="cm"):
    """Shaxsiy kategoriyalar. category_id ga ishonilmaydi — egasi bazada tekshiriladi."""

    action: str  # add | del | delok | cancel
    category_id: int = 0


def manage_keyboard(custom: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    """custom: (id, yorliq). Limitga yetilmagan bo'lsa — qo'shish tugmasi."""
    b = InlineKeyboardBuilder()
    if len(custom) < MAX_CUSTOM_CATEGORIES:
        b.button(text=CATEGORY_ADD, callback_data=CategoryAction(action="add"))
    for category_id, label in custom:
        b.button(
            text=f"🗑 {label}", callback_data=CategoryAction(action="del", category_id=category_id)
        )
    b.adjust(1)
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
