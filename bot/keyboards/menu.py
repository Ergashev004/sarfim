from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from bot.constants import (
    MENU_CATEGORIES,
    MENU_EXPENSE,
    MENU_HISTORY,
    MENU_INCOME,
    MENU_PLACEHOLDER,
    MENU_REPORTS,
)


def main_menu() -> ReplyKeyboardMarkup:
    """Pastki doimiy menyu. Faqat yordamchi: "taksi 25000" tugmasiz ham ishlaydi."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=MENU_EXPENSE)],
            [KeyboardButton(text=MENU_INCOME), KeyboardButton(text=MENU_REPORTS)],
            [KeyboardButton(text=MENU_HISTORY), KeyboardButton(text=MENU_CATEGORIES)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder=MENU_PLACEHOLDER,
    )
