"""Handler'lar soxta Message/CallbackQuery bilan, lekin haqiqiy baza va FSM bilan."""

from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import time_machine
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import func, select

from bot.db import repo
from bot.db.models import Category, Transaction, TransactionSource, TransactionType, User
from bot.handlers.entry import (
    CANCELLED,
    NOT_FOUND,
    STALE,
    EntryForm,
    on_amount_reply,
    on_pending_category,
    on_text,
    on_tx_action,
)
from bot.keyboards.entry import PendingCategory, TxAction
from bot.middlewares.db import DbMiddleware

TZ = ZoneInfo("Asia/Tashkent")
TODAY = date(2026, 10, 11)


@pytest.fixture(autouse=True)
def frozen_time():
    with time_machine.travel(datetime(2026, 10, 11, 12, 0, tzinfo=TZ), tick=False):
        yield


class FakeMessage:
    def __init__(self, text: str | None = None) -> None:
        self.text = text
        self.answers: list[tuple[str, object]] = []
        self.edits: list[tuple[str, object]] = []
        self.markups: list[object] = []

    async def answer(self, text, reply_markup=None, **_):
        self.answers.append((text, reply_markup))

    async def edit_text(self, text, reply_markup=None, **_):
        self.edits.append((text, reply_markup))

    async def edit_reply_markup(self, reply_markup=None, **_):
        self.markups.append(reply_markup)


class FakeCallback:
    def __init__(self) -> None:
        self.message = FakeMessage()
        self.alerts: list[str | None] = []

    async def answer(self, text=None, show_alert=False, **_):
        self.alerts.append(text)


def _state(user_id: int) -> FSMContext:
    return FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=user_id, user_id=user_id))


@pytest.fixture
async def me(session) -> User:
    user = await repo.get_or_create_user(session, 1001, "Akobir")
    await session.commit()
    return user


@pytest.fixture
async def stranger(session) -> User:
    user = await repo.get_or_create_user(session, 2002, "Begona")
    await session.commit()
    return user


@pytest.fixture
def state() -> FSMContext:
    return _state(1001)


async def send(text, state, session, user) -> FakeMessage:
    message = FakeMessage(text)
    handler = on_amount_reply if await state.get_state() == EntryForm.amount.state else on_text
    await handler(message, state, session, user, TZ)
    return message


async def press(data, session, user, state=None) -> FakeCallback:
    callback = FakeCallback()
    if isinstance(data, PendingCategory):
        state = state or _state(user.telegram_id)
        await on_pending_category(callback, data, state, session, user, TZ)
    else:
        await on_tx_action(callback, data, session, user, TZ)
    return callback


async def _transactions(session) -> list[Transaction]:
    # populate_existing: sessiyadagi eski nusxalar o'rniga bazadagi holatni o'qiymiz
    stmt = select(Transaction).order_by(Transaction.id).execution_options(populate_existing=True)
    return list(await session.scalars(stmt))


async def _category_id(session, name: str) -> int:
    return (await repo.get_default_category(session, name)).id


# ---------------------------------------------------------------------------
# Matn -> saqlash
# ---------------------------------------------------------------------------


async def test_expense_saved_and_card_shown(session, me, state):
    message = await send("taksi 30000", state, session, me)

    [tx] = await _transactions(session)
    assert (tx.type, tx.amount, tx.occurred_on) == (TransactionType.EXPENSE, 30_000, TODAY)
    assert tx.category_id == await _category_id(session, "Transport")
    assert tx.source is TransactionSource.KEYWORD
    assert tx.note == "taksi 30000"

    [(text, markup)] = message.answers
    assert "30 000 so'm" in text and "Transport" in text
    assert "qoldiq" not in text  # kirim yo'q
    assert len(markup.inline_keyboard[0]) == 3


async def test_balance_shown_after_income(session, me, state):
    await send("+5 mln oylik", state, session, me)
    message = await send("taksi 30000", state, session, me)
    assert "Umumiy qoldiq: <b>4 970 000 so'm</b>" in message.answers[0][0]


async def test_income_card_has_no_category_button(session, me, state):
    message = await send("+5 mln oylik", state, session, me)
    [tx] = await _transactions(session)
    assert tx.category_id is None
    assert len(message.answers[0][1].inline_keyboard[0]) == 2


async def test_bad_date_rejected(session, me, state):
    message = await send("taksi 30000 05.09", state, session, me)
    assert "30 kun" in message.answers[0][0]
    assert await _transactions(session) == []


# ---------------------------------------------------------------------------
# Summani so'rash
# ---------------------------------------------------------------------------


async def test_missing_amount_asked_then_saved(session, me, state):
    first = await send("kecha taksi", state, session, me)
    assert "Summani yozing" in first.answers[0][0]
    assert await state.get_state() == EntryForm.amount.state
    assert await _transactions(session) == []

    await send("25k", state, session, me)
    [tx] = await _transactions(session)
    assert (tx.amount, tx.occurred_on) == (25_000, date(2026, 10, 10))
    assert await state.get_state() is None


async def test_multiple_numbers_asks_amount(session, me, state):
    first = await send("2 ta non 5000", state, session, me)
    assert "bir nechta raqam" in first.answers[0][0]
    await send("5000", state, session, me)
    [tx] = await _transactions(session)
    assert tx.amount == 5_000
    assert tx.category_id == await _category_id(session, "Oziq-ovqat")


async def test_two_dates_asks_amount_then_category(session, me, state):
    first = await send("5.10 kecha", state, session, me)
    assert "ikkita sana" in first.answers[0][0]

    second = await send("30000", state, session, me)
    assert "qaysi kategoriyaga" in second.answers[0][0]
    assert await _transactions(session) == []

    kiyim = await _category_id(session, "Kiyim")
    await press(PendingCategory(category_id=kiyim), session, me, state)
    [tx] = await _transactions(session)
    assert (tx.amount, tx.category_id, tx.occurred_on) == (30_000, kiyim, date(2026, 10, 10))
    assert tx.source is TransactionSource.MANUAL


async def test_invalid_amount_reply_keeps_waiting(session, me, state):
    await send("taksi", state, session, me)
    message = await send("0", state, session, me)
    assert "0 dan katta" in message.answers[0][0]
    assert await state.get_state() == EntryForm.amount.state


async def test_non_amount_reply_treated_as_new_entry(session, me, state):
    await send("taksi", state, session, me)
    await send("kino 40000", state, session, me)  # 2 ta raqam emas, bitta — summa bo'lib ketadi
    [tx] = await _transactions(session)
    assert tx.category_id == await _category_id(session, "Transport")

    await send("taksi", state, session, me)
    await send("salom", state, session, me)  # raqam yo'q — yangi yozuv, yana summa so'raladi
    assert await state.get_state() == EntryForm.amount.state
    assert len(await _transactions(session)) == 1


# ---------------------------------------------------------------------------
# Kategoriyasi noaniq yozuv
# ---------------------------------------------------------------------------


async def test_unknown_category_not_saved_until_chosen(session, me, state):
    message = await send("taksi non 20000", state, session, me)
    assert await _transactions(session) == []
    labels = [b.text for row in message.answers[0][1].inline_keyboard for b in row]
    assert len(labels) == 11 and "🚕 Transport" in labels

    transport = await _category_id(session, "Transport")
    callback = await press(PendingCategory(category_id=transport), session, me, state)
    [tx] = await _transactions(session)
    assert tx.category_id == transport
    assert "Transport" in callback.message.edits[0][0]


async def test_pending_category_double_press_saves_once(session, me, state):
    await send("30000", state, session, me)
    data = PendingCategory(category_id=await _category_id(session, "Kiyim"))
    await press(data, session, me, state)
    second = await press(data, session, me, state)
    assert second.alerts == [STALE]
    assert len(await _transactions(session)) == 1


async def test_pending_category_by_stranger_is_stale(session, me, stranger, state):
    await send("30000", state, session, me)
    callback = await press(  # begonaning FSM holati bo'sh
        PendingCategory(category_id=await _category_id(session, "Kiyim")), session, stranger
    )
    assert callback.alerts == [STALE]
    assert await _transactions(session) == []


async def test_pending_foreign_custom_category_rejected(session, me, stranger, state):
    foreign = Category(user_id=stranger.id, name="Baliq")
    session.add(foreign)
    await session.commit()
    await send("30000", state, session, me)
    callback = await press(PendingCategory(category_id=foreign.id), session, me, state)
    assert "tanlab bo'lmaydi" in callback.alerts[0]
    assert await _transactions(session) == []


# ---------------------------------------------------------------------------
# Bekor qilish: egasi va ikki marta bosish
# ---------------------------------------------------------------------------


async def _saved_tx(session, me, state, text="taksi 30000") -> Transaction:
    await send(text, state, session, me)
    return (await _transactions(session))[-1]


async def test_cancel_deletes_record(session, me, state):
    tx = await _saved_tx(session, me, state)
    callback = await press(TxAction(action="cancel", tx_id=tx.id), session, me)
    assert await _transactions(session) == []
    assert callback.message.edits == [(CANCELLED, None)]


async def test_cancel_twice_no_error(session, me, state):
    tx = await _saved_tx(session, me, state)
    data = TxAction(action="cancel", tx_id=tx.id)
    await press(data, session, me)
    second = await press(data, session, me)
    assert second.alerts == [NOT_FOUND]
    assert second.message.edits == []


async def test_cancel_by_stranger_rejected(session, me, stranger, state):
    tx = await _saved_tx(session, me, state)
    callback = await press(TxAction(action="cancel", tx_id=tx.id), session, stranger)
    assert callback.alerts == [NOT_FOUND]
    assert len(await _transactions(session)) == 1


@pytest.mark.parametrize(
    ("action", "value"),
    [("cat", 0), ("date", 0), ("back", 0), ("setcat", 1), ("setdate", TODAY.toordinal() - 1)],
)
async def test_stranger_cannot_touch_record(session, me, stranger, state, action, value):
    tx = await _saved_tx(session, me, state)
    before = (tx.category_id, tx.occurred_on)
    callback = await press(TxAction(action=action, tx_id=tx.id, value=value), session, stranger)
    assert callback.alerts == [NOT_FOUND]
    assert callback.message.edits == [] and callback.message.markups == []
    [after] = await _transactions(session)
    assert (after.category_id, after.occurred_on) == before


# ---------------------------------------------------------------------------
# Kategoriya va sanani o'zgartirish
# ---------------------------------------------------------------------------


async def test_change_category(session, me, state):
    tx = await _saved_tx(session, me, state)
    opened = await press(TxAction(action="cat", tx_id=tx.id), session, me)
    assert len(opened.message.markups) == 1

    kafe = await _category_id(session, "Kafe/restoran")
    callback = await press(TxAction(action="setcat", tx_id=tx.id, value=kafe), session, me)
    [after] = await _transactions(session)
    assert after.category_id == kafe
    assert after.source is TransactionSource.MANUAL
    assert "Kafe/restoran" in callback.message.edits[0][0]


async def test_foreign_custom_category_rejected(session, me, stranger, state):
    foreign = Category(user_id=stranger.id, name="Baliq")
    session.add(foreign)
    await session.commit()
    tx = await _saved_tx(session, me, state)
    callback = await press(TxAction(action="setcat", tx_id=tx.id, value=foreign.id), session, me)
    assert "tanlab bo'lmaydi" in callback.alerts[0]
    [after] = await _transactions(session)
    assert after.category_id != foreign.id


async def test_income_category_change_refused(session, me, state):
    tx = await _saved_tx(session, me, state, "+5 mln oylik")
    callback = await press(TxAction(action="cat", tx_id=tx.id), session, me)
    assert "Kirimga kategoriya" in callback.alerts[0]


async def test_change_date(session, me, state):
    tx = await _saved_tx(session, me, state)
    picker = await press(TxAction(action="date", tx_id=tx.id), session, me)
    assert picker.message.markups[0].inline_keyboard[0][1].text == "Kecha"

    new_date = date(2026, 9, 11)  # 30-kun — ruxsat
    callback = await press(
        TxAction(action="setdate", tx_id=tx.id, value=new_date.toordinal()), session, me
    )
    [after] = await _transactions(session)
    assert after.occurred_on == new_date
    assert "11.09.2026" in callback.message.edits[0][0]


@pytest.mark.parametrize(
    "value", [date(2026, 9, 10).toordinal(), date(2026, 10, 12).toordinal(), 0, 10**9]
)
async def test_change_date_outside_window_refused(session, me, state, value):
    tx = await _saved_tx(session, me, state)
    callback = await press(TxAction(action="setdate", tx_id=tx.id, value=value), session, me)
    assert "tanlab bo'lmaydi" in callback.alerts[0]
    [after] = await _transactions(session)
    assert after.occurred_on == TODAY


# ---------------------------------------------------------------------------
# Middleware: /start va har bir update foydalanuvchini bir marta yozadi
# ---------------------------------------------------------------------------


async def test_middleware_creates_user_once(sessionmaker):
    middleware = DbMiddleware(sessionmaker)
    seen = []

    async def handler(event, data):
        seen.append((data["session"], data["db_user"].telegram_id))

    tg_user = SimpleNamespace(id=777, first_name="Akobir")
    await middleware(handler, object(), {"event_from_user": tg_user})
    await middleware(handler, object(), {"event_from_user": tg_user})

    assert [tid for _, tid in seen] == [777, 777]
    async with sessionmaker() as s:
        assert await s.scalar(select(func.count()).select_from(User)) == 1
