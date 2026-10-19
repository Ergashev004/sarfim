"""Pastki menyu: /start yuboradi, har tugmaning handler'i bor, kutilgan kiritish bekor bo'ladi."""

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from aiogram.types import Chat, Message, ReplyKeyboardMarkup

from bot.handlers import menu
from bot.handlers.categories import CategoryForm
from bot.handlers.entry import EntryForm
from bot.handlers.menu import on_menu_categories, on_menu_history, on_menu_report
from bot.handlers.report import CHOOSE_PERIOD, ReportForm
from bot.handlers.start import cmd_start
from bot.keyboards.menu import main_menu
from bot.services.history import EMPTY
from tests.fakes import FakeMessage

TZ = ZoneInfo("Asia/Tashkent")


def _labels() -> list[str]:
    return [b.text for row in main_menu().keyboard for b in row]


async def test_start_sends_menu():
    message = FakeMessage("/start")
    message.from_user = SimpleNamespace(first_name="Akobir")
    await cmd_start(message)
    [(_, markup)] = message.answers
    assert isinstance(markup, ReplyKeyboardMarkup)
    assert markup.is_persistent and markup.resize_keyboard


@pytest.mark.parametrize("label", _labels())
async def test_every_button_has_exactly_one_handler(label):
    msg = Message(message_id=1, date=datetime.now(), chat=Chat(id=1, type="private"), text=label)
    matched = [h for h in menu.router.message.handlers if (await h.check(msg))[0]]
    assert len(matched) == 1


async def test_report_button(state):
    message = FakeMessage("📊 Hisobot")
    await on_menu_report(message, state)
    [(text, _)] = message.answers
    assert text == CHOOSE_PERIOD


async def test_history_button(session, me, state):
    message = FakeMessage("🕘 Oxirgi yozuvlar")
    await on_menu_history(message, state, session, me, TZ)
    assert message.answers == [(EMPTY, None)]


async def test_categories_button(session, me, state):
    message = FakeMessage("📂 Kategoriyalar")
    await on_menu_categories(message, state, session, me)
    [(text, _)] = message.answers
    assert "Oziq-ovqat" in text


@pytest.mark.parametrize("waiting", [ReportForm.range, CategoryForm.name])
async def test_button_cancels_waiting_input(state, waiting):
    await state.set_state(waiting)
    await on_menu_report(FakeMessage("📊 Hisobot"), state)
    assert await state.get_state() is None


async def test_button_keeps_unsaved_entry(state):
    await state.set_state(EntryForm.category)
    await on_menu_report(FakeMessage("📊 Hisobot"), state)
    assert await state.get_state() == EntryForm.category.state
