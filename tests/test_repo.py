from datetime import date

from sqlalchemy import func, select

from bot.db import repo
from bot.db.models import Category, TransactionSource, TransactionType, User

DAY = date(2026, 10, 11)


async def _add(session, user, kind, amount, category_id=None):
    return await repo.add_transaction(
        session,
        user_id=user.id,
        kind=kind,
        amount=amount,
        occurred_on=DAY,
        source=TransactionSource.KEYWORD,
        category_id=category_id,
    )


async def _transport(session) -> Category:
    return await repo.get_default_category(session, "Transport")


# ---------------------------------------------------------------------------
# Foydalanuvchi
# ---------------------------------------------------------------------------


async def test_get_or_create_user_is_idempotent(session):
    a = await repo.get_or_create_user(session, 555, "Akobir")
    b = await repo.get_or_create_user(session, 555, "Akobir")
    await session.commit()
    assert a.id == b.id
    assert await session.scalar(select(func.count()).select_from(User)) == 1


async def test_get_or_create_user_updates_name(session):
    await repo.get_or_create_user(session, 555, "Old")
    user = await repo.get_or_create_user(session, 555, "New")
    assert user.first_name == "New"


# ---------------------------------------------------------------------------
# Qoldiq
# ---------------------------------------------------------------------------


async def test_balance_none_without_income(session):
    user = await repo.get_or_create_user(session, 1, None)
    await _add(session, user, TransactionType.EXPENSE, 30_000, (await _transport(session)).id)
    assert await repo.get_balance(session, user.id) is None


async def test_balance_income_minus_expense(session):
    user = await repo.get_or_create_user(session, 1, None)
    transport = await _transport(session)
    await _add(session, user, TransactionType.INCOME, 5_000_000)
    await _add(session, user, TransactionType.EXPENSE, 30_000, transport.id)
    await _add(session, user, TransactionType.EXPENSE, 1_250_000, transport.id)
    assert await repo.get_balance(session, user.id) == 3_720_000


async def test_balance_can_be_negative(session):
    user = await repo.get_or_create_user(session, 1, None)
    await _add(session, user, TransactionType.INCOME, 100_000)
    await _add(session, user, TransactionType.EXPENSE, 150_000, (await _transport(session)).id)
    assert await repo.get_balance(session, user.id) == -50_000


async def test_balance_is_per_user(session):
    me = await repo.get_or_create_user(session, 1, None)
    other = await repo.get_or_create_user(session, 2, None)
    await _add(session, me, TransactionType.INCOME, 100_000)
    await _add(session, other, TransactionType.INCOME, 9_000_000)
    await _add(session, other, TransactionType.EXPENSE, 10_000, (await _transport(session)).id)
    assert await repo.get_balance(session, me.id) == 100_000


async def test_balance_large_sums_stay_int(session):
    user = await repo.get_or_create_user(session, 1, None)
    for _ in range(5):
        await _add(session, user, TransactionType.INCOME, 1_000_000_000)
    balance = await repo.get_balance(session, user.id)
    assert balance == 5_000_000_000
    assert isinstance(balance, int)


# ---------------------------------------------------------------------------
# Egalik
# ---------------------------------------------------------------------------


async def test_get_own_transaction_rejects_other_user(session):
    owner = await repo.get_or_create_user(session, 1, None)
    stranger = await repo.get_or_create_user(session, 2, None)
    tx = await _add(session, owner, TransactionType.INCOME, 1000)
    assert await repo.get_own_transaction(session, tx.id, owner.id) is not None
    assert await repo.get_own_transaction(session, tx.id, stranger.id) is None


async def test_delete_own_transaction(session):
    owner = await repo.get_or_create_user(session, 1, None)
    stranger = await repo.get_or_create_user(session, 2, None)
    tx = await _add(session, owner, TransactionType.INCOME, 1000)

    assert await repo.delete_own_transaction(session, tx.id, stranger.id) is False
    assert await repo.delete_own_transaction(session, tx.id, owner.id) is True
    assert await repo.delete_own_transaction(session, tx.id, owner.id) is False  # 2-marta


async def test_categories_visible_to_user(session):
    me = await repo.get_or_create_user(session, 1, None)
    other = await repo.get_or_create_user(session, 2, None)
    mine = Category(user_id=me.id, name="Mashina")
    theirs = Category(user_id=other.id, name="Baliq")
    session.add_all([mine, theirs])
    await session.flush()

    names = [c.name for c in await repo.list_categories(session, me.id)]
    assert len(names) == 12
    assert names[-1] == "Mashina"  # standartlardan keyin
    assert "Baliq" not in names
    assert await repo.get_category(session, me.id, theirs.id) is None
    assert await repo.get_category(session, me.id, mine.id) is not None
