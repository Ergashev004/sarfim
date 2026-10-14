from datetime import date

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.card import RELATIVE_DAYS


class TxAction(CallbackData, prefix="tx"):
    """Saqlangan yozuv ustidagi amal. tx_id ga ishonilmaydi — egasi bazada tekshiriladi."""

    action: str  # cancel | cat | date | setcat | setdate | back
    tx_id: int
    value: int = 0  # setcat: category_id, setdate: date.toordinal()


class PendingCategory(CallbackData, prefix="pc"):
    """Hali saqlanmagan (kategoriyasi aniq bo'lmagan) yozuv uchun kategoriya tanlash."""

    category_id: int


class AiConfirm(CallbackData, prefix="ai"):
    """AI topgan summani tasdiqlash. Yozuv FSM'da (foydalanuvchi bo'yicha) — ID kerak emas."""

    ok: bool


def ai_confirm_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Ha, saqlash", callback_data=AiConfirm(ok=True))
    b.button(text="✏️ Summani o'zim yozaman", callback_data=AiConfirm(ok=False))
    b.adjust(1)
    return b.as_markup()


def card_keyboard(tx_id: int, *, with_category: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="↩️ Bekor qilish", callback_data=TxAction(action="cancel", tx_id=tx_id))
    if with_category:
        b.button(text="📂 Kategoriya", callback_data=TxAction(action="cat", tx_id=tx_id))
    b.button(text="📅 Sana", callback_data=TxAction(action="date", tx_id=tx_id))
    return b.as_markup()


def _back(tx_id: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text="⬅️ Orqaga", callback_data=TxAction(action="back", tx_id=tx_id).pack()
    )


def category_keyboard(
    categories: list[tuple[int, str]], tx_id: int | None = None
) -> InlineKeyboardMarkup:
    """tx_id bo'lsa — saqlangan yozuv kategoriyasini o'zgartirish, bo'lmasa — yangi yozuv."""
    b = InlineKeyboardBuilder()
    for category_id, label in categories:
        if tx_id is None:
            data = PendingCategory(category_id=category_id)
        else:
            data = TxAction(action="setcat", tx_id=tx_id, value=category_id)
        b.button(text=label, callback_data=data)
    b.adjust(2)
    if tx_id is not None:
        b.row(_back(tx_id))
    return b.as_markup()


def date_keyboard(tx_id: int, dates: list[date]) -> InlineKeyboardMarkup:
    """Birinchi qator: Bugun / Kecha / O'tgan kuni, pastida qolgan kunlar 4 tadan."""
    b = InlineKeyboardBuilder()

    def button(value: date, text: str) -> InlineKeyboardButton:
        data = TxAction(action="setdate", tx_id=tx_id, value=value.toordinal())
        return InlineKeyboardButton(text=text, callback_data=data.pack())

    top = [button(d, RELATIVE_DAYS[i].capitalize()) for i, d in enumerate(dates[:3])]
    b.row(*top)
    rest = [button(d, d.strftime("%d.%m")) for d in dates[3:]]
    for i in range(0, len(rest), 4):
        b.row(*rest[i : i + 4])
    b.row(_back(tx_id))
    return b.as_markup()
