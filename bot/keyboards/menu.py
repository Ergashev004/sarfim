from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

MENU_REPORT = "📊 Hisobot"
MENU_HISTORY = "🕘 Oxirgi yozuvlar"
MENU_CATEGORIES = "📂 Kategoriyalar"


def main_menu() -> ReplyKeyboardMarkup:
    """Pastki doimiy menyu. Xarajat/kirim tugmasiz — erkin matn bilan yoziladi."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=MENU_REPORT), KeyboardButton(text=MENU_HISTORY)],
            [KeyboardButton(text=MENU_CATEGORIES)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Masalan: taksi 30000",
    )
