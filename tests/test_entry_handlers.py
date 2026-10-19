"""Handler'lar soxta Message/CallbackQuery bilan, lekin haqiqiy baza va FSM bilan."""

from datetime import date
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from bot.db import repo
from bot.db.models import Category, Transaction, TransactionSource, TransactionType, User
from bot.handlers.entry import (
    ASK_NEW_AMOUNT,
    DELETED,
    NOT_FOUND,
    STALE,
    EditForm,
    EntryForm,
    on_amount_reply,
    on_edit_amount,
    on_income,
    on_pending_category,
    on_text,
    on_tx_action,
)
from bot.keyboards.entry import PendingCategory, TxAction
from bot.middlewares.db import DbMiddleware
from tests.fakes import FakeCallback, FakeMessage, make_state

TZ = ZoneInfo("Asia/Tashkent")
TODAY = date(2026, 10, 11)


pytestmark = pytest.mark.usefixtures("frozen_time")

_state = make_state


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
        await on_tx_action(callback, data, session, user, TZ, state)
    return callback


def _actions(markup) -> list[str]:
    return [TxAction.unpack(b.callback_data).action for row in markup.inline_keyboard for b in row]


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
    assert _actions(markup) == ["ok", "cat"]  # [To'g'ri] [O'zgartirish]


async def test_balance_shown_after_income(session, me, state):
    await send("+5 mln oylik", state, session, me)
    message = await send("taksi 30000", state, session, me)
    assert "Umumiy qoldiq: <b>4 970 000 so'm</b>" in message.answers[0][0]


async def test_income_card_has_no_category_button(session, me, state):
    message = await send("+5 mln oylik", state, session, me)
    [tx] = await _transactions(session)
    assert tx.category_id is None
    assert _actions(message.answers[0][1]) == ["edit", "del"]  # tasdiqlanadigan kategoriya yo'q


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
    text, markup = callback.message.edits[0]
    assert "Transport" in text
    assert _actions(markup) == ["edit", "del"]  # o'zi tanladi — tasdiq shart emas


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
# O'chirish: tasdiq, egasi va ikki marta bosish
# ---------------------------------------------------------------------------


async def _saved_tx(session, me, state, text="taksi 30000") -> Transaction:
    await send(text, state, session, me)
    return (await _transactions(session))[-1]


@pytest.mark.parametrize("action", ["del", "cancel"])  # cancel — eski kartalardagi tugma
async def test_delete_asks_confirmation_first(session, me, state, action):
    tx = await _saved_tx(session, me, state)
    callback = await press(TxAction(action=action, tx_id=tx.id), session, me)
    assert len(await _transactions(session)) == 1
    assert _actions(callback.message.markups[0]) == ["delok", "back"]


async def test_delete_confirmed(session, me, state):
    tx = await _saved_tx(session, me, state)
    callback = await press(TxAction(action="delok", tx_id=tx.id), session, me)
    assert await _transactions(session) == []
    assert callback.message.edits == [(DELETED, None)]


async def test_delete_cancelled_keeps_record(session, me, state):
    tx = await _saved_tx(session, me, state)
    callback = await press(TxAction(action="back", tx_id=tx.id), session, me)
    assert len(await _transactions(session)) == 1
    assert _actions(callback.message.markups[0]) == ["edit", "del"]


async def test_delete_twice_no_error(session, me, state):
    tx = await _saved_tx(session, me, state)
    data = TxAction(action="delok", tx_id=tx.id)
    await press(data, session, me)
    second = await press(data, session, me)
    assert second.alerts == [NOT_FOUND]
    assert second.message.edits == []


async def test_delete_by_stranger_rejected(session, me, stranger, state):
    tx = await _saved_tx(session, me, state)
    callback = await press(TxAction(action="delok", tx_id=tx.id), session, stranger)
    assert callback.alerts == [NOT_FOUND]
    assert len(await _transactions(session)) == 1


@pytest.mark.parametrize(
    ("action", "value"),
    [
        ("ok", 0),
        ("edit", 0),
        ("del", 0),
        ("amount", 0),
        ("open", 0),
        ("cat", 0),
        ("date", 0),
        ("back", 0),
        ("setcat", 1),
        ("setdate", TODAY.toordinal() - 1),
    ],
)
async def test_stranger_cannot_touch_record(session, me, stranger, state, action, value):
    tx = await _saved_tx(session, me, state)
    before = (tx.category_id, tx.occurred_on)
    their_state = make_state(stranger.telegram_id)
    callback = await press(
        TxAction(action=action, tx_id=tx.id, value=value), session, stranger, their_state
    )
    assert callback.alerts == [NOT_FOUND]
    assert callback.message.edits == [] and callback.message.markups == []
    assert callback.message.answers == []
    assert await their_state.get_state() is None
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
    [(note, markup)] = callback.message.answers  # alohida xabar
    assert "Kategoriya o'zgartirildi" in note
    assert "Kafe/restoran" in note
    assert markup is None


async def test_same_category_sends_no_message(session, me, state):
    tx = await _saved_tx(session, me, state)
    callback = await press(
        TxAction(action="setcat", tx_id=tx.id, value=tx.category_id), session, me
    )
    assert callback.message.answers == []
    assert callback.alerts == ["Kategoriya o'zgarmadi"]
    [after] = await _transactions(session)
    assert after.source is not TransactionSource.MANUAL


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
# Kategoriyani tasdiqlash, tahrirlash menyusi, summa
# ---------------------------------------------------------------------------


async def test_category_ok_switches_to_record_buttons(session, me, state):
    tx = await _saved_tx(session, me, state)
    callback = await press(TxAction(action="ok", tx_id=tx.id), session, me)
    text, markup = callback.message.edits[0]
    assert "Transport" in text
    assert _actions(markup) == ["edit", "del"]
    [after] = await _transactions(session)
    assert after.source is TransactionSource.KEYWORD  # lug'atdan — o'rganish shart emas
    assert await repo.find_user_keyword_categories(session, me.id, ["taksi"]) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("taksi 30000", ["amount", "cat", "date", "back"]),
        ("+5 mln oylik", ["amount", "date", "back"]),
    ],
)
async def test_edit_menu(session, me, state, text, expected):
    tx = await _saved_tx(session, me, state, text)
    callback = await press(TxAction(action="edit", tx_id=tx.id), session, me)
    assert _actions(callback.message.markups[0]) == expected


async def _ask_amount(session, me, state) -> Transaction:
    tx = await _saved_tx(session, me, state)
    callback = await press(TxAction(action="amount", tx_id=tx.id), session, me, state)
    assert callback.message.answers == [(ASK_NEW_AMOUNT, None)]
    assert await state.get_state() == EditForm.amount.state
    return tx


async def _reply_amount(text, state, session, me) -> FakeMessage:
    message = FakeMessage(text)
    await on_edit_amount(message, state, session, me, TZ)
    return message


async def test_edit_amount(session, me, state):
    await _ask_amount(session, me, state)
    message = await _reply_amount("45 ming", state, session, me)
    [after] = await _transactions(session)
    assert after.amount == 45_000
    assert await state.get_state() is None
    [(text, markup)] = message.answers
    assert "45 000 so'm" in text and _actions(markup) == ["edit", "del"]


async def test_edit_amount_invalid_keeps_waiting(session, me, state):
    await _ask_amount(session, me, state)
    message = await _reply_amount("0", state, session, me)
    assert "0 dan katta" in message.answers[0][0]
    assert await state.get_state() == EditForm.amount.state
    [after] = await _transactions(session)
    assert after.amount == 30_000


async def test_edit_amount_non_amount_is_new_entry(session, me, state):
    await _ask_amount(session, me, state)
    await _reply_amount("2 ta non 5000", state, session, me)  # ikki raqam — yangi yozuv
    [after] = await _transactions(session)
    assert after.amount == 30_000
    assert await state.get_state() == EntryForm.amount.state  # yangi yozuv summasi so'raldi


async def test_edit_amount_record_deleted_meanwhile(session, me, state):
    tx = await _ask_amount(session, me, state)
    await press(TxAction(action="delok", tx_id=tx.id), session, me)
    message = await _reply_amount("45000", state, session, me)
    assert message.answers == [(NOT_FOUND, None)]
    assert await state.get_state() is None


# ---------------------------------------------------------------------------
# "💰 Daromad" bosilgandan keyin: + shart emas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["5 mln oylik", "+5 mln oylik", "5000000"])
async def test_income_after_menu_button(session, me, state, text):
    await state.set_state(EntryForm.income)
    message = FakeMessage(text)
    await on_income(message, state, session, me, TZ)
    [tx] = await _transactions(session)
    assert (tx.type, tx.amount) == (TransactionType.INCOME, 5_000_000)
    assert "Kirim saqlandi" in message.answers[0][0]
    assert await state.get_state() is None


async def test_income_without_amount_asks_amount(session, me, state):
    await state.set_state(EntryForm.income)
    await on_income(FakeMessage("oylik"), state, session, me, TZ)
    assert await state.get_state() == EntryForm.amount.state
    message = await send("5 mln", state, session, me)
    [tx] = await _transactions(session)
    assert tx.type is TransactionType.INCOME
    assert "Kirim saqlandi" in message.answers[0][0]


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
