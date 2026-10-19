from datetime import date

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.constants import (
    AI_NO,
    AI_YES,
    BACK,
    CATEGORY_CHANGE,
    CATEGORY_OK,
    DELETE_NO,
    DELETE_YES,
    EDIT_AMOUNT,
    EDIT_CATEGORY,
    EDIT_DATE,
    RECORD_DELETE,
    RECORD_EDIT,
)
from bot.services.card import RELATIVE_DAYS


class TxAction(CallbackData, prefix="tx"):
    """Saqlangan yozuv ustidagi amal. tx_id ga ishonilmaydi — egasi bazada tekshiriladi.

    ok — kategoriya to'g'ri; cat/setcat — kategoriya; edit — tahrirlash menyusi;
    amount — summa; date/setdate — sana; del/delok — o'chirish; back — yozuv tugmalari;
    open — /oxirgi ro'yxatidan karta.
    """

    action: str
    tx_id: int
    value: int = 0  # setcat: category_id, setdate: date.toordinal()


class PendingCategory(CallbackData, prefix="pc"):
    """Hali saqlanmagan (kategoriyasi aniq bo'lmagan) yozuv uchun kategoriya tanlash."""

    category_id: int


class AiConfirm(CallbackData, prefix="ai"):
    """AI topgan summani tasdiqlash. Yozuv FSM'da (foydalanuvchi bo'yicha) — ID kerak emas."""

    ok: bool


def _tx(text: str, action: str, tx_id: int, value: int = 0) -> InlineKeyboardButton:
    data = TxAction(action=action, tx_id=tx_id, value=value)
    return InlineKeyboardButton(text=text, callback_data=data.pack())


def ai_confirm_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=AI_YES, callback_data=AiConfirm(ok=True))
    b.button(text=AI_NO, callback_data=AiConfirm(ok=False))
    b.adjust(1)
    return b.as_markup()


def confirm_keyboard(tx_id: int) -> InlineKeyboardMarkup:
    """Yangi xarajat: bot tanlagan kategoriya to'g'rimi."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[_tx(CATEGORY_OK, "ok", tx_id), _tx(CATEGORY_CHANGE, "cat", tx_id)]]
    )


def record_keyboard(tx_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_tx(RECORD_EDIT, "edit", tx_id), _tx(RECORD_DELETE, "del", tx_id)]]
    )


def edit_keyboard(tx_id: int, *, with_category: bool) -> InlineKeyboardMarkup:
    row = [_tx(EDIT_AMOUNT, "amount", tx_id)]
    if with_category:
        row.append(_tx(EDIT_CATEGORY, "cat", tx_id))
    row.append(_tx(EDIT_DATE, "date", tx_id))
    return InlineKeyboardMarkup(inline_keyboard=[row, [_tx(BACK, "back", tx_id)]])


def delete_confirm_keyboard(tx_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_tx(DELETE_YES, "delok", tx_id), _tx(DELETE_NO, "back", tx_id)]]
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
        b.row(_tx(BACK, "back", tx_id))
    return b.as_markup()


def date_keyboard(tx_id: int, dates: list[date]) -> InlineKeyboardMarkup:
    """Birinchi qator: Bugun / Kecha / O'tgan kuni, pastida qolgan kunlar 4 tadan."""
    b = InlineKeyboardBuilder()
    top = [
        _tx(RELATIVE_DAYS[i].capitalize(), "setdate", tx_id, d.toordinal())
        for i, d in enumerate(dates[:3])
    ]
    b.row(*top)
    rest = [_tx(d.strftime("%d.%m"), "setdate", tx_id, d.toordinal()) for d in dates[3:]]
    for i in range(0, len(rest), 4):
        b.row(*rest[i : i + 4])
    b.row(_tx(BACK, "back", tx_id))
    return b.as_markup()


def history_keyboard(tx_ids: list[int]) -> InlineKeyboardMarkup:
    """/oxirgi: har yozuvga raqamli tugma (5 tadan), bosilsa yozuv kartasi ochiladi."""
    b = InlineKeyboardBuilder()
    for i, tx_id in enumerate(tx_ids, 1):
        b.button(text=str(i), callback_data=TxAction(action="open", tx_id=tx_id))
    b.adjust(5)
    return b.as_markup()
