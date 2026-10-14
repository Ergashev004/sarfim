"""Shaxsiy kategoriyalar: nomni tekshirish, qo'shish, o'chirish (yozuvlar "Boshqa"ga)."""

import pytest
from sqlalchemy import select

from bot.db import repo
from bot.db.models import Category, TransactionSource, TransactionType, UserKeyword
from bot.handlers.categories import (
    ASK_NAME,
    CANCELLED,
    NOT_FOUND,
    CategoryForm,
    cmd_categories,
    on_category_action,
    on_category_name,
)
from bot.keyboards.categories import CategoryAction
from bot.services.categories import (
    MAX_CUSTOM_CATEGORIES,
    clean_category_name,
    validate_category_name,
)
from tests.fakes import FakeCallback, FakeMessage, make_state
from tests.test_entry_handlers import TODAY

pytestmark = pytest.mark.usefixtures("frozen_time")

# ---------------------------------------------------------------------------
# Nomni tekshirish (servis)
# ---------------------------------------------------------------------------


def test_clean_name():
    assert clean_category_name("  sport   zali ") == "Sport zali"


@pytest.mark.parametrize(
    ("name", "count", "error_part"),
    [
        ("Sport", 0, None),
        ("Sport", MAX_CUSTOM_CATEGORIES, "Ko'pi bilan"),
        ("S", 0, "belgidan"),
        ("S" * 33, 0, "belgidan"),
        ("12345", 0, "harf"),
        ("/start", 0, "harf"),
        ("transport", 0, "allaqachon"),  # standart bilan, katta-kichik harfga qaramay
        ("TRANSPORT", 0, "allaqachon"),
    ],
)
def test_validate_name(name, count, error_part):
    error = validate_category_name(name, ["Transport", "Boshqa"], count)
    if error_part is None:
        assert error is None
    else:
        assert error_part in error


# ---------------------------------------------------------------------------
# Handler'lar
# ---------------------------------------------------------------------------


async def act(action, session, user, state, category_id=0) -> FakeCallback:
    callback = FakeCallback()
    data = CategoryAction(action=action, category_id=category_id)
    await on_category_action(callback, data, state, session, user)
    return callback


async def type_name(text, session, user, state) -> FakeMessage:
    message = FakeMessage(text)
    await on_category_name(message, state, session, user)
    return message


async def _custom(session, user) -> list[Category]:
    stmt = select(Category).where(Category.user_id == user.id).order_by(Category.id)
    return list(await session.scalars(stmt.execution_options(populate_existing=True)))


async def test_add_category(session, me, state):
    callback = await act("add", session, me, state)
    assert callback.message.answers[0][0] == ASK_NAME
    assert await state.get_state() == CategoryForm.name.state

    message = await type_name("  sport ", session, me, state)
    assert "«Sport» kategoriyasi qo'shildi" in message.answers[0][0]
    assert await state.get_state() is None
    [cat] = await _custom(session, me)
    assert (cat.name, cat.emoji) == ("Sport", "🏷")
    assert "1/3" in message.answers[1][0]


async def test_bad_name_keeps_waiting(session, me, state):
    await act("add", session, me, state)
    message = await type_name("Transport", session, me, state)
    assert "allaqachon" in message.answers[0][0]
    assert await state.get_state() == CategoryForm.name.state
    assert await _custom(session, me) == []


async def test_same_name_allowed_for_other_user(session, me, stranger, state):
    await repo.add_custom_category(session, stranger.id, "Sport", None)
    await act("add", session, me, state)
    await type_name("Sport", session, me, state)
    assert [c.name for c in await _custom(session, me)] == ["Sport"]


async def test_limit_three(session, me, state):
    for name in ("Sport", "Mashina", "Kitoblar"):
        await act("add", session, me, state)
        await type_name(name, session, me, state)
    await act("add", session, me, state)
    message = await type_name("Bog'", session, me, state)
    assert "Ko'pi bilan 3" in message.answers[0][0]
    assert len(await _custom(session, me)) == 3

    # Limitda "qo'shish" tugmasi chiqmaydi
    overview = FakeMessage()
    await cmd_categories(overview, session, me, state)
    _, markup = overview.answers[0]
    texts = [b.text for row in markup.inline_keyboard for b in row]
    assert not any("qo'shish" in t for t in texts)
    assert sum(t.startswith("🗑") for t in texts) == 3


async def test_cancel_add(session, me, state):
    await act("add", session, me, state)
    callback = await act("cancel", session, me, state)
    assert callback.message.edits[0][0] == CANCELLED
    assert await state.get_state() is None


async def test_command_keeps_pending_entry(session, me, state):
    """/kategoriyalar saqlanmagan xarajatni (kategoriya kutilayotgan) yo'qotmaydi."""
    from bot.handlers.entry import EntryForm

    await state.set_state(EntryForm.category)
    await cmd_categories(FakeMessage(), session, me, state)
    assert await state.get_state() == EntryForm.category.state


async def _expense_in(session, user, category_id, amount=5000):
    tx = await repo.add_transaction(
        session,
        user_id=user.id,
        kind=TransactionType.EXPENSE,
        amount=amount,
        occurred_on=TODAY,
        source=TransactionSource.MANUAL,
        category_id=category_id,
    )
    await session.commit()
    return tx


async def test_delete_moves_records_to_fallback(session, me, state):
    sport = await repo.add_custom_category(session, me.id, "Sport", "🏷")
    await repo.save_user_keyword(session, me.id, "trenajor", sport.id)
    await _expense_in(session, me, sport.id)
    await _expense_in(session, me, sport.id)

    callback = await act("del", session, me, state, sport.id)
    text, markup = callback.message.edits[0]
    assert "2 ta yozuv «Boshqa»ga o'tadi" in text
    assert await _custom(session, me) != []  # tasdiqsiz o'chmaydi

    callback = await act("delok", session, me, state, sport.id)
    assert "2 ta yozuv «Boshqa»ga o'tdi" in callback.message.edits[0][0]
    assert await _custom(session, me) == []
    other = await repo.get_default_category(session, "Boshqa")
    txs = await repo_transactions(session, me)
    assert [t.category_id for t in txs] == [other.id, other.id]
    assert await session.scalar(select(UserKeyword)) is None  # CASCADE


async def repo_transactions(session, user):
    from bot.db.models import Transaction

    stmt = select(Transaction).where(Transaction.user_id == user.id)
    return list(await session.scalars(stmt.execution_options(populate_existing=True)))


async def test_delete_twice_no_error(session, me, state):
    sport = await repo.add_custom_category(session, me.id, "Sport", None)
    await session.commit()
    await act("delok", session, me, state, sport.id)
    callback = await act("delok", session, me, state, sport.id)
    assert callback.alerts == [NOT_FOUND]


@pytest.mark.parametrize("action", ["del", "delok"])
async def test_stranger_cannot_delete(session, me, stranger, state, action):
    sport = await repo.add_custom_category(session, me.id, "Sport", None)
    await _expense_in(session, me, sport.id)
    callback = await act(action, session, stranger, make_state(stranger.telegram_id), sport.id)
    assert callback.alerts == [NOT_FOUND]
    assert [c.name for c in await _custom(session, me)] == ["Sport"]


@pytest.mark.parametrize("action", ["del", "delok"])
async def test_default_category_cannot_be_deleted(session, me, state, action):
    transport = await repo.get_default_category(session, "Transport")
    callback = await act(action, session, me, state, transport.id)
    assert callback.alerts == [NOT_FOUND]
    assert await repo.get_default_category(session, "Transport") is not None


async def test_custom_category_usable_for_entries(session, me, state):
    """Shaxsiy kategoriya tugmalarda chiqadi va tanlansa saqlanadi."""
    from bot.handlers.entry import on_pending_category, on_text
    from bot.keyboards.entry import PendingCategory
    from tests.test_entry_handlers import TZ

    sport = await repo.add_custom_category(session, me.id, "Sport", "🏷")
    await session.commit()
    message = FakeMessage("trenajor 50000")
    await on_text(message, state, session, me, TZ)
    _, markup = message.answers[0]
    assert "🏷 Sport" in [b.text for row in markup.inline_keyboard for b in row]

    await on_pending_category(
        FakeCallback(), PendingCategory(category_id=sport.id), state, session, me, TZ
    )
    # Keyingi safar o'rganilgan so'z orqali darhol saqlanadi
    message = FakeMessage("trenajor 70000")
    await on_text(message, state, session, me, TZ)
    assert "🏷 Sport" in message.answers[0][0]
