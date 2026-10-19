"""Pastki menyu tugmalari. Router boshqalardan oldin turadi — tugma matni xarajat deb o'qilmasin
va kutilayotgan kiritish (kategoriya nomi, oraliq) tugma matnini olib qo'ymasin."""

from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.handlers.categories import CategoryForm, cmd_categories
from bot.handlers.history import cmd_last
from bot.handlers.report import ReportForm, cmd_report
from bot.keyboards.menu import MENU_CATEGORIES, MENU_HISTORY, MENU_REPORT

router = Router(name="menu")

# Tugma bosilsa shu kutishlar bekor bo'ladi; saqlanmagan xarajat (EntryForm) esa qoladi
_INPUT_STATES = {CategoryForm.name.state, ReportForm.range.state}


async def _leave_input(state: FSMContext) -> None:
    if await state.get_state() in _INPUT_STATES:
        await state.clear()


@router.message(F.text == MENU_REPORT)
async def on_menu_report(message: Message, state: FSMContext) -> None:
    await _leave_input(state)
    await cmd_report(message)


@router.message(F.text == MENU_HISTORY)
async def on_menu_history(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User, tz: ZoneInfo
) -> None:
    await _leave_input(state)
    await cmd_last(message, session, db_user, tz)


@router.message(F.text == MENU_CATEGORIES)
async def on_menu_categories(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User
) -> None:
    await _leave_input(state)
    await cmd_categories(message, session, db_user)
