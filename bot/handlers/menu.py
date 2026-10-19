"""Pastki menyu tugmalari — faqat yordamchi: "taksi 25000" tugmasiz ham ishlaydi.

Router boshqalardan oldin turadi — tugma matni xarajat deb o'qilmasin va kutilayotgan kiritish
(kategoriya nomi, oraliq, yangi summa) tugma matnini olib qo'ymasin.
"""

from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import MENU_EXPENSE, MENU_HISTORY, MENU_INCOME, MENU_REPORTS, MENU_SETTINGS
from bot.db.models import User
from bot.handlers.categories import CategoryForm, cmd_categories
from bot.handlers.entry import ASK_INCOME, EditForm, EntryForm
from bot.handlers.history import cmd_last
from bot.handlers.report import ReportForm, cmd_report

router = Router(name="menu")

EXPENSE_HINT = (
    "✍️ Xarajatni oddiy matn bilan yozing:\n"
    "<code>taksi 25000</code>\n"
    "<code>non 8000 kecha</code>\n\n"
    "<i>Tugmani bosish shart emas — istalgan payt shunchaki yozing.</i>"
)

# Tugma bosilsa shu kutishlar bekor bo'ladi; saqlanmagan xarajat (summa/kategoriya kutilayotgan)
# esa qoladi
_INPUT_STATES = {
    CategoryForm.name.state,
    ReportForm.range.state,
    EntryForm.income.state,
    EditForm.amount.state,
}


async def _leave_input(state: FSMContext) -> None:
    if await state.get_state() in _INPUT_STATES:
        await state.clear()


@router.message(F.text == MENU_EXPENSE)
async def on_menu_expense(message: Message, state: FSMContext) -> None:
    await _leave_input(state)
    await message.answer(EXPENSE_HINT)


@router.message(F.text == MENU_INCOME)
async def on_menu_income(message: Message, state: FSMContext) -> None:
    await _leave_input(state)
    await state.set_state(EntryForm.income)
    await message.answer(ASK_INCOME)


@router.message(F.text == MENU_REPORTS)
async def on_menu_reports(message: Message, state: FSMContext) -> None:
    await _leave_input(state)
    await cmd_report(message)


@router.message(F.text == MENU_HISTORY)
async def on_menu_history(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User, tz: ZoneInfo
) -> None:
    await _leave_input(state)
    await cmd_last(message, session, db_user, tz)


@router.message(F.text == MENU_SETTINGS)
async def on_menu_settings(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User
) -> None:
    # Hozircha sozlamalar = kategoriyalarni boshqarish (shaxsiy qo'shish/o'chirish)
    await _leave_input(state)
    await cmd_categories(message, session, db_user)
