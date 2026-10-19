"""Pastki menyu: /start yuboradi, har tugmaning handler'i bor, kutilgan kiritish bekor bo'ladi."""

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from aiogram.types import Chat, Message, ReplyKeyboardMarkup

from bot import constants
from bot.handlers import menu
from bot.handlers.categories import CategoryForm
from bot.handlers.entry import ASK_INCOME, EditForm, EntryForm
from bot.handlers.menu import (
    EXPENSE_HINT,
    on_menu_categories,
    on_menu_expense,
    on_menu_history,
    on_menu_income,
    on_menu_reports,
)
from bot.handlers.report import CHOOSE_PERIOD, ReportForm
from bot.handlers.start import cmd_start
from bot.keyboards.menu import main_menu
from bot.services.entry import EntryStatus, parse_entry
from bot.services.history import EMPTY
from tests.fakes import FakeMessage

TZ = ZoneInfo("Asia/Tashkent")


def _labels() -> list[str]:
    return [b.text for row in main_menu().keyboard for b in row]


def test_menu_layout():
    rows = [[b.text for b in row] for row in main_menu().keyboard]
    assert rows == [
        [constants.MENU_EXPENSE],
        [constants.MENU_INCOME, constants.MENU_REPORTS],
        [constants.MENU_HISTORY, constants.MENU_CATEGORIES],
    ]
    assert main_menu().resize_keyboard


async def test_start_sends_menu():
    message = FakeMessage("/start")
    message.from_user = SimpleNamespace(first_name="Akobir")
    await cmd_start(message)
    [(_, markup)] = message.answers
    assert isinstance(markup, ReplyKeyboardMarkup)
    assert _labels() == [b.text for row in markup.keyboard for b in row]


@pytest.mark.parametrize("label", _labels())
async def test_every_button_has_exactly_one_handler(label):
    msg = Message(message_id=1, date=datetime.now(), chat=Chat(id=1, type="private"), text=label)
    matched = [h for h in menu.router.message.handlers if (await h.check(msg))[0]]
    assert len(matched) == 1


@pytest.mark.parametrize("label", _labels())
def test_button_text_is_not_a_complete_entry(label):
    """Menyu router'i bo'lmasa ham tugma matni xarajat bo'lib saqlanib ketmaydi."""
    assert parse_entry(label, datetime.now().date()).status is not EntryStatus.READY


async def test_expense_button_only_hints(state):
    message = FakeMessage(constants.MENU_EXPENSE)
    await on_menu_expense(message, state)
    assert message.answers == [(EXPENSE_HINT, None)]
    assert await state.get_state() is None  # keyingi matn oddiy yo'l bilan o'qiladi


async def test_income_button_waits_for_income(state):
    message = FakeMessage(constants.MENU_INCOME)
    await on_menu_income(message, state)
    assert message.answers == [(ASK_INCOME, None)]
    assert await state.get_state() == EntryForm.income.state


async def test_reports_button(state):
    message = FakeMessage(constants.MENU_REPORTS)
    await on_menu_reports(message, state)
    [(text, markup)] = message.answers
    assert text == CHOOSE_PERIOD
    assert [b.text for row in markup.inline_keyboard for b in row] == [
        "Bu oy",
        "Bu yil",
        "Boshqa davr",
    ]


async def test_history_button(session, me, state):
    message = FakeMessage(constants.MENU_HISTORY)
    await on_menu_history(message, state, session, me, TZ)
    assert message.answers == [(EMPTY, None)]


async def test_categories_button(session, me, state):
    message = FakeMessage(constants.MENU_CATEGORIES)
    await on_menu_categories(message, state, session, me)
    [(text, _)] = message.answers
    assert "Oziq-ovqat" in text


@pytest.mark.parametrize(
    "waiting", [ReportForm.range, CategoryForm.name, EntryForm.income, EditForm.amount]
)
async def test_button_cancels_waiting_input(state, waiting):
    await state.set_state(waiting)
    await on_menu_reports(FakeMessage(constants.MENU_REPORTS), state)
    assert await state.get_state() is None


async def test_button_keeps_unsaved_entry(state):
    await state.set_state(EntryForm.category)
    await on_menu_reports(FakeMessage(constants.MENU_REPORTS), state)
    assert await state.get_state() == EntryForm.category.state


async def test_expense_button_cancels_income_wait(state):
    await state.set_state(EntryForm.income)
    await on_menu_expense(FakeMessage(constants.MENU_EXPENSE), state)
    assert await state.get_state() is None
