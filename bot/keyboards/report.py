from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.report import PeriodKind

PERIOD_LABELS = {
    PeriodKind.TODAY: "Bugun",
    PeriodKind.WEEK: "Bu hafta",
    PeriodKind.MONTH: "Bu oy",
    PeriodKind.MONTHS_3: "3 oy",
    PeriodKind.MONTHS_6: "6 oy",
    PeriodKind.YEAR: "Bu yil",
    PeriodKind.CUSTOM: "📅 Davr tanlash",
}


class ReportPeriod(CallbackData, prefix="rp"):
    """Hisobot davri. ID yo'q — hisobot doim bosgan foydalanuvchining o'zi uchun."""

    kind: PeriodKind


def period_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for kind, label in PERIOD_LABELS.items():
        b.button(text=label, callback_data=ReportPeriod(kind=kind))
    b.adjust(2, 2, 2, 1)
    return b.as_markup()
