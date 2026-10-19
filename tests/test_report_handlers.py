"""/hisobot va /oxirgi handler'lari: soxta Message/CallbackQuery, haqiqiy baza va FSM."""

from datetime import date
from zoneinfo import ZoneInfo

import pytest
from aiogram.dispatcher.event.bases import SkipHandler

from bot.db import repo
from bot.db.models import TransactionSource, TransactionType
from bot.handlers import report as report_handlers
from bot.handlers.entry import NOT_FOUND, EntryForm, on_tx_action
from bot.handlers.history import cmd_last
from bot.handlers.report import ASK_RANGE, ReportForm, cmd_report, on_period, on_range
from bot.keyboards.entry import TxAction
from bot.keyboards.report import ReportPeriod
from bot.services.history import EMPTY
from bot.services.report import RANGE_ERRORS, PeriodKind, RangeStatus
from tests.fakes import FakeCallback, FakeMessage

TZ = ZoneInfo("Asia/Tashkent")
TODAY = date(2026, 10, 11)
PNG = b"\x89PNG\r\n\x1a\n"

pytestmark = pytest.mark.usefixtures("frozen_time")


async def _add(session, user, kind, amount, day=TODAY, category="Transport", note=None):
    category_id = None
    if kind is TransactionType.EXPENSE:
        category_id = (await repo.get_default_category(session, category)).id
    tx = await repo.add_transaction(
        session,
        user_id=user.id,
        kind=kind,
        amount=amount,
        occurred_on=day,
        source=TransactionSource.KEYWORD,
        category_id=category_id,
        note=note,
    )
    await session.commit()
    return tx


async def press(kind, session, user, state) -> FakeCallback:
    callback = FakeCallback()
    await on_period(callback, ReportPeriod(kind=kind), state, session, user, TZ)
    return callback


# ---------------------------------------------------------------------------
# /hisobot
# ---------------------------------------------------------------------------


async def test_command_shows_period_buttons():
    message = FakeMessage("/hisobot")
    await cmd_report(message)
    [(_, markup)] = message.answers
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert len(buttons) == len(PeriodKind)
    assert ReportPeriod.unpack(buttons[-1].callback_data).kind is PeriodKind.CUSTOM


async def test_month_report_photo_with_caption(session, me, state):
    await _add(session, me, TransactionType.INCOME, 5_000_000)
    await _add(session, me, TransactionType.EXPENSE, 30_000, date(2026, 10, 2))
    await _add(session, me, TransactionType.EXPENSE, 90_000, category="Oziq-ovqat")
    await _add(session, me, TransactionType.EXPENSE, 70_000, date(2026, 9, 30))  # o'tgan oy

    callback = await press(PeriodKind.MONTH, session, me, state)

    assert callback.alerts == [None]  # tugma darhol javob oldi
    [(photo, caption)] = callback.message.photos
    assert photo.data.startswith(PNG)
    assert "1–11 oktabr 2026" in caption
    assert "Chiqim:  120 000 so'm" in caption
    assert "Oziq-ovqat — 90 000 so'm (75%)" in caption
    assert callback.message.answers == []


async def test_long_text_sent_after_photo(session, me, state, monkeypatch):
    await _add(session, me, TransactionType.EXPENSE, 30_000)
    monkeypatch.setattr(report_handlers, "fits_caption", lambda _: False)

    callback = await press(PeriodKind.MONTH, session, me, state)

    [(_, caption)] = callback.message.photos
    assert caption is None
    [(text, _)] = callback.message.answers
    assert "30 000 so'm" in text


async def test_income_only_text_without_chart(session, me, state):
    await _add(session, me, TransactionType.INCOME, 5_000_000)
    callback = await press(PeriodKind.TODAY, session, me, state)
    assert callback.message.photos == []
    [(text, _)] = callback.message.answers
    assert "Kirim:  5 000 000 so'm" in text


async def test_empty_period(session, me, state):
    callback = await press(PeriodKind.WEEK, session, me, state)
    [(text, _)] = callback.message.answers
    assert "Bu davrda yozuv yo'q." in text


async def test_stranger_records_not_counted(session, me, stranger, state):
    await _add(session, stranger, TransactionType.EXPENSE, 999_000)
    await _add(session, stranger, TransactionType.INCOME, 5_000_000)
    callback = await press(PeriodKind.MONTH, session, me, state)
    [(text, _)] = callback.message.answers
    assert "Bu davrda yozuv yo'q." in text
    assert "qoldiq" not in text


# ---------------------------------------------------------------------------
# Ixtiyoriy oraliq
# ---------------------------------------------------------------------------


async def test_custom_range_flow(session, me, state):
    await _add(session, me, TransactionType.EXPENSE, 30_000, date(2026, 10, 3))
    await _add(
        session, me, TransactionType.EXPENSE, 50_000, date(2026, 10, 8)
    )  # oraliqdan tashqarida

    callback = await press(PeriodKind.CUSTOM, session, me, state)
    assert callback.message.answers == [(ASK_RANGE, None)]
    assert await state.get_state() == ReportForm.range.state

    message = FakeMessage("1.10 - 5.10")
    await on_range(message, state, session, me, TZ)

    assert await state.get_state() is None
    [(_, caption)] = message.photos
    assert "1–5 oktabr 2026" in caption
    assert "Chiqim:  30 000 so'm" in caption


@pytest.mark.parametrize(
    ("text", "status"),
    [
        ("12.10.2026 - 20.10.2026", RangeStatus.FUTURE),
        ("10.10.2026 - 1.10.2026", RangeStatus.REVERSED),
        ("31.02 - 5.10", RangeStatus.INVALID),
        ("1.10 taksi 5.10", RangeStatus.BAD_FORMAT),
    ],
)
async def test_bad_range_keeps_waiting(session, me, state, text, status):
    await state.set_state(ReportForm.range)
    message = FakeMessage(text)
    await on_range(message, state, session, me, TZ)
    assert message.answers == [(RANGE_ERRORS[status], None)]
    assert message.photos == []
    assert await state.get_state() == ReportForm.range.state


async def test_text_without_dates_goes_to_entry_flow(session, me, state):
    await state.set_state(ReportForm.range)
    message = FakeMessage("taksi 30000")
    with pytest.raises(SkipHandler):
        await on_range(message, state, session, me, TZ)
    assert await state.get_state() is None
    assert message.answers == []


async def test_command_cancels_only_range_wait(state):
    await state.set_state(ReportForm.range)
    await cmd_report(FakeMessage("/hisobot"), state)
    assert await state.get_state() is None

    await state.set_state(EntryForm.category)  # saqlanmagan xarajat yo'qolmasin
    await cmd_report(FakeMessage("/hisobot"), state)
    assert await state.get_state() == EntryForm.category.state


# ---------------------------------------------------------------------------
# /oxirgi
# ---------------------------------------------------------------------------


async def test_last_empty(session, me):
    message = FakeMessage("/oxirgi")
    await cmd_last(message, session, me, TZ)
    assert message.answers == [(EMPTY, None)]


async def test_last_lists_own_newest_first(session, me, stranger):
    for i in range(12):
        await _add(session, me, TransactionType.EXPENSE, 1000 + i, note=f"yozuv {i}")
    await _add(session, stranger, TransactionType.EXPENSE, 777_000, note="begona")

    message = FakeMessage("/oxirgi")
    await cmd_last(message, session, me, TZ)

    [(text, markup)] = message.answers
    assert "<b>1.</b> 💸 1 011 so'm" in text  # eng oxirgisi birinchi
    assert "<b>10.</b> 💸 1 002 so'm" in text
    assert "1 001 so'm" not in text and "begona" not in text
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert [b.text for b in buttons] == [str(i) for i in range(1, 11)]
    assert [len(row) for row in markup.inline_keyboard] == [5, 5]


async def test_open_from_history_shows_card(session, me):
    tx = await _add(session, me, TransactionType.EXPENSE, 30_000, note="taksi 30000")
    callback = FakeCallback()
    await on_tx_action(callback, TxAction(action="open", tx_id=tx.id), session, me, TZ)
    [(text, markup)] = callback.message.answers
    assert "30 000 so'm" in text and "Transport" in text
    assert len(markup.inline_keyboard[0]) == 3


async def test_open_foreign_record_refused(session, me, stranger):
    tx = await _add(session, me, TransactionType.EXPENSE, 30_000)
    callback = FakeCallback()
    await on_tx_action(callback, TxAction(action="open", tx_id=tx.id), session, stranger, TZ)
    assert callback.alerts == [NOT_FOUND]
    assert callback.message.answers == []


async def test_range_end_in_future_clamped_to_today(session, me, state):
    await _add(session, me, TransactionType.EXPENSE, 30_000, date(2026, 10, 5))
    await state.set_state(ReportForm.range)
    message = FakeMessage("1.10 - 20.10")
    await on_range(message, state, session, me, TZ)
    [(_, caption)] = message.photos
    assert "1–11 oktabr 2026" in caption
