"""AI, tasdiq va user_keywords — handler'lar orqali, haqiqiy baza va FSM bilan."""

import pytest

from bot.db.models import TransactionSource
from bot.handlers.entry import (
    AI_REJECTED,
    STALE,
    EntryForm,
    on_ai_confirm,
    on_amount_reply,
    on_text,
)
from bot.keyboards.entry import AiConfirm, PendingCategory, TxAction
from tests.fakes import FakeCallback, FakeMessage, gateway, make_state
from tests.test_entry_handlers import TZ, _category_id, _transactions, press

pytestmark = pytest.mark.usefixtures("frozen_time")


async def send(text, state, session, user, ai=None) -> FakeMessage:
    message = FakeMessage(text)
    handler = on_amount_reply if await state.get_state() == EntryForm.amount.state else on_text
    await handler(message, state, session, user, TZ, ai)
    return message


async def confirm(ok, state, session, user) -> FakeCallback:
    callback = FakeCallback()
    await on_ai_confirm(callback, AiConfirm(ok=ok), state, session, user, TZ)
    return callback


# ---------------------------------------------------------------------------
# AI kategoriya
# ---------------------------------------------------------------------------


async def test_ai_category_saved_immediately(session, me, state):
    ai, _ = gateway({"category": "Transport", "amount": 0})
    message = await send("velosiped 300000", state, session, me, ai)
    [tx] = await _transactions(session)
    assert tx.source is TransactionSource.AI
    assert tx.category_id == await _category_id(session, "Transport")
    text, _ = message.answers[0]
    assert "AI tanladi" in text


async def test_ai_unavailable_shows_buttons(session, me, state):
    ai, _ = gateway(TimeoutError())
    message = await send("velosiped 300000", state, session, me, ai)
    assert await _transactions(session) == []
    assert await state.get_state() == EntryForm.category.state
    assert "qaysi kategoriyaga" in message.answers[0][0]


async def test_keyword_card_has_no_ai_hint(session, me, state):
    message = await send("taksi 30000", state, session, me)
    assert "AI" not in message.answers[0][0]


async def test_fixing_ai_category_makes_it_manual(session, me, state):
    ai, _ = gateway({"category": "Transport", "amount": 0})
    await send("velosiped 300000", state, session, me, ai)
    [tx] = await _transactions(session)
    kiyim = await _category_id(session, "Kiyim")
    callback = await press(TxAction(action="setcat", tx_id=tx.id, value=kiyim), session, me)
    [tx] = await _transactions(session)
    assert (tx.category_id, tx.source) == (kiyim, TransactionSource.MANUAL)
    assert "AI" not in callback.message.edits[0][0]


# ---------------------------------------------------------------------------
# Kalit so'zni o'rganish
# ---------------------------------------------------------------------------


async def test_manual_choice_is_learned(session, me, state):
    await send("velosiped 300000", state, session, me)  # AI yo'q -> tugmalar
    sport = await _category_id(session, "Ko'ngilochar")
    await press(PendingCategory(category_id=sport), session, me, state)

    ai, client = gateway()
    message = await send("velosiped 150000", state, session, me, ai)
    assert client.calls == []  # AI chaqirilmadi
    _, second = await _transactions(session)
    assert (second.category_id, second.source) == (sport, TransactionSource.KEYWORD)
    assert "Xarajat saqlandi" in message.answers[0][0]


async def test_card_correction_is_learned(session, me, state):
    ai, _ = gateway({"category": "Transport", "amount": 0})
    await send("velosiped 300000", state, session, me, ai)
    [tx] = await _transactions(session)
    kiyim = await _category_id(session, "Kiyim")
    await press(TxAction(action="setcat", tx_id=tx.id, value=kiyim), session, me)

    await send("velosiped 100000", state, session, me)
    _, second = await _transactions(session)
    assert second.category_id == kiyim


async def test_learned_word_is_private(session, me, stranger, state):
    await send("velosiped 300000", state, session, me)
    await press(
        PendingCategory(category_id=await _category_id(session, "Kiyim")), session, me, state
    )

    their_state = make_state(stranger.telegram_id)
    await send("velosiped 100000", their_state, session, stranger)
    assert await their_state.get_state() == EntryForm.category.state


# ---------------------------------------------------------------------------
# Bir nechta raqam -> AI summa -> tasdiq
# ---------------------------------------------------------------------------


async def test_ai_amount_not_saved_before_confirm(session, me, state):
    ai, _ = gateway({"category": "Transport", "amount": 10000})
    message = await send("2 ta velosiped 5000 dan", state, session, me, ai)
    assert await _transactions(session) == []
    assert await state.get_state() == EntryForm.confirm.state
    text, markup = message.answers[0]
    assert "10 000 so'm" in text and "Transport" in text
    assert markup is not None


async def test_confirm_saves_ai_amount(session, me, state):
    ai, _ = gateway({"category": "Transport", "amount": 10000})
    await send("2 ta velosiped 5000 dan", state, session, me, ai)
    callback = await confirm(True, state, session, me)
    [tx] = await _transactions(session)
    assert (tx.amount, tx.source) == (10000, TransactionSource.AI)
    assert tx.category_id == await _category_id(session, "Transport")
    assert "Xarajat saqlandi" in callback.message.answers[0][0]
    assert await state.get_state() is None


async def test_confirm_without_category_asks_category(session, me, state):
    ai, _ = gateway({"category": "unknown", "amount": 10000})
    await send("2 ta velosiped 5000 dan", state, session, me, ai)
    callback = await confirm(True, state, session, me)
    assert await _transactions(session) == []
    assert await state.get_state() == EntryForm.category.state
    assert "10 000 so'm" in callback.message.answers[0][0]

    kiyim = await _category_id(session, "Kiyim")
    await press(PendingCategory(category_id=kiyim), session, me, state)
    [tx] = await _transactions(session)
    assert (tx.amount, tx.category_id, tx.source) == (10000, kiyim, TransactionSource.MANUAL)


async def test_reject_asks_amount_manually(session, me, state):
    ai, _ = gateway({"category": "Transport", "amount": 10000})
    await send("2 ta velosiped 5000 dan", state, session, me, ai)
    callback = await confirm(False, state, session, me)
    assert callback.message.edits[0][0] == AI_REJECTED
    assert await state.get_state() == EntryForm.amount.state
    assert await _transactions(session) == []

    # Summa yozilgach AI'ning kategoriyasiga ham ishonilmaydi — tugmalar
    await send("5000", state, session, me)
    assert await state.get_state() == EntryForm.category.state


async def test_reject_keeps_keyword_category(session, me, state):
    ai, _ = gateway({"category": "Transport", "amount": 10000})
    await send("2 ta non 5000", state, session, me, ai)
    await confirm(False, state, session, me)
    await send("5000", state, session, me)
    [tx] = await _transactions(session)
    assert (tx.amount, tx.category_id) == (5000, await _category_id(session, "Oziq-ovqat"))


async def test_confirm_double_press_saves_once(session, me, state):
    ai, _ = gateway({"category": "Transport", "amount": 10000})
    await send("2 ta velosiped 5000 dan", state, session, me, ai)
    await confirm(True, state, session, me)
    callback = await confirm(True, state, session, me)
    assert callback.alerts == [STALE]
    assert len(await _transactions(session)) == 1


async def test_confirm_by_stranger_is_stale(session, me, stranger, state):
    ai, _ = gateway({"category": "Transport", "amount": 10000})
    await send("2 ta velosiped 5000 dan", state, session, me, ai)
    callback = await confirm(True, make_state(stranger.telegram_id), session, stranger)
    assert callback.alerts == [STALE]
    assert await _transactions(session) == []


async def test_new_text_replaces_pending_confirm(session, me, state):
    ai, _ = gateway({"category": "Transport", "amount": 10000})
    await send("2 ta velosiped 5000 dan", state, session, me, ai)
    await send("taksi 30000", state, session, me)
    [tx] = await _transactions(session)
    assert tx.amount == 30000
    callback = await confirm(True, state, session, me)
    assert callback.alerts == [STALE]


async def test_repeated_correction_of_dictionary_word(session, me, state):
    """Lug'atdagi so'z ("osh" -> Kafe/restoran) tuzatilsa, eng oxirgi tuzatish ustun."""
    kafe = await _category_id(session, "Kafe/restoran")
    food = await _category_id(session, "Oziq-ovqat")

    await send("osh 30000", state, session, me)
    [tx] = await _transactions(session)
    assert tx.category_id == kafe  # hali hech narsa o'rganilmagan — lug'at

    await press(TxAction(action="setcat", tx_id=tx.id, value=food), session, me)
    await send("osh 25000", state, session, me)
    second = (await _transactions(session))[-1]
    assert (second.category_id, second.source) == (food, TransactionSource.KEYWORD)

    await press(TxAction(action="setcat", tx_id=second.id, value=kafe), session, me)
    await send("kecha osh 20000", state, session, me)
    third = (await _transactions(session))[-1]
    assert third.category_id == kafe
    assert "Kafe/restoran" in (await send("osh 15000", state, session, me)).answers[0][0]
