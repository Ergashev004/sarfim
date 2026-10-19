from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.constants import REPORT_CUSTOM, REPORT_MONTH, REPORT_YEAR
from bot.services.report import PeriodKind

PERIOD_LABELS = {
    PeriodKind.MONTH: REPORT_MONTH,
    PeriodKind.YEAR: REPORT_YEAR,
    PeriodKind.CUSTOM: REPORT_CUSTOM,
}


class ReportPeriod(CallbackData, prefix="rp"):
    """Hisobot davri. ID yo'q — hisobot doim bosgan foydalanuvchining o'zi uchun."""

    kind: PeriodKind


def period_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for kind, label in PERIOD_LABELS.items():
        b.button(text=label, callback_data=ReportPeriod(kind=kind))
    b.adjust(2, 1)
    return b.as_markup()
