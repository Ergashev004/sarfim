from datetime import date

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError

from bot.db.models import (
    Category,
    Transaction,
    TransactionSource,
    TransactionType,
    User,
    UserKeyword,
)

DAY = date(2026, 10, 11)


async def _user(session, telegram_id: int = 1001) -> User:
    user = User(telegram_id=telegram_id, first_name="Akobir")
    session.add(user)
    await session.flush()
    return user


async def _category(session, name: str = "Transport") -> Category:
    return await session.scalar(
        select(Category).where(Category.user_id.is_(None), Category.name == name)
    )


def _expense(user: User, category: Category | None, amount: int = 30_000) -> Transaction:
    return Transaction(
        user_id=user.id,
        type=TransactionType.EXPENSE,
        amount=amount,
        category_id=category.id if category else None,
        occurred_on=DAY,
        source=TransactionSource.KEYWORD,
    )


def _income(user: User, category_id: int | None = None) -> Transaction:
    return Transaction(
        user_id=user.id,
        type=TransactionType.INCOME,
        amount=5_000_000,
        category_id=category_id,
        occurred_on=DAY,
        source=TransactionSource.KEYWORD,
    )


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------


async def test_user_defaults(session):
    user = await _user(session)
    await session.commit()
    await session.refresh(user)
    assert user.timezone == "Asia/Tashkent"
    assert user.created_at is not None


async def test_telegram_id_is_unique(session):
    await _user(session, 42)
    with pytest.raises(IntegrityError):
        await _user(session, 42)


async def test_telegram_id_fits_bigint(session):
    user = await _user(session, 8_000_000_000)  # 32-bit int'dan katta
    await session.commit()
    assert await session.scalar(select(User.telegram_id).where(User.id == user.id)) == 8_000_000_000


# ---------------------------------------------------------------------------
# transactions
# ---------------------------------------------------------------------------


async def test_expense_saved_with_defaults(session):
    user = await _user(session)
    tx = _expense(user, await _category(session), amount=1_000_000_000)
    session.add(tx)
    await session.commit()

    row = (await session.execute(select(Transaction))).scalar_one()
    assert row.currency == "UZS"
    assert row.amount == 1_000_000_000
    assert isinstance(row.amount, int)
    assert row.type is TransactionType.EXPENSE
    assert row.source is TransactionSource.KEYWORD


async def test_enum_stored_as_lowercase_value(session):
    user = await _user(session)
    session.add(_expense(user, await _category(session)))
    await session.commit()
    raw = (await session.execute(text("SELECT type, source FROM transactions"))).one()
    assert tuple(raw) == ("expense", "keyword")


async def test_income_without_category_ok(session):
    user = await _user(session)
    session.add(_income(user))
    await session.commit()


async def test_expense_requires_category(session):
    user = await _user(session)
    session.add(_expense(user, None))
    with pytest.raises(IntegrityError, match="category_matches_type"):
        await session.flush()


async def test_income_must_not_have_category(session):
    user = await _user(session)
    category = await _category(session)
    session.add(_income(user, category.id))
    with pytest.raises(IntegrityError, match="category_matches_type"):
        await session.flush()


@pytest.mark.parametrize("amount", [0, -100])
async def test_amount_must_be_positive(session, amount):
    user = await _user(session)
    session.add(_expense(user, await _category(session), amount=amount))
    with pytest.raises(IntegrityError, match="amount_positive"):
        await session.flush()


@pytest.mark.parametrize(
    ("column", "value"),
    [("type", "transfer"), ("source", "magic")],
)
async def test_unknown_enum_value_rejected(session, column, value):
    user = await _user(session)
    category = await _category(session)
    values = {"type": "expense", "source": "manual", column: value}
    with pytest.raises(IntegrityError):
        await session.execute(
            text(
                "INSERT INTO transactions (user_id, type, amount, category_id, occurred_on, source)"
                " VALUES (:u, :t, 1000, :c, '2026-10-11', :s)"
            ),
            {"u": user.id, "t": values["type"], "c": category.id, "s": values["source"]},
        )


async def test_unknown_user_rejected(session):
    """SQLite'da tashqi kalitlar yoqilganini tekshiradi (PRAGMA foreign_keys)."""
    session.add(
        Transaction(
            user_id=999,
            type=TransactionType.INCOME,
            amount=1,
            occurred_on=DAY,
            source=TransactionSource.MANUAL,
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


# ---------------------------------------------------------------------------
# categories
# ---------------------------------------------------------------------------


async def test_custom_category_name_unique_per_user(session):
    user = await _user(session)
    session.add(Category(user_id=user.id, name="Mashina"))
    await session.flush()
    session.add(Category(user_id=user.id, name="Mashina"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_same_custom_name_for_different_users_ok(session):
    a = await _user(session, 1)
    b = await _user(session, 2)
    session.add_all(
        [Category(user_id=a.id, name="Mashina"), Category(user_id=b.id, name="Mashina")]
    )
    await session.commit()


async def test_default_category_name_cannot_repeat(session):
    session.add(Category(user_id=None, name="Transport"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_category_with_transactions_cannot_be_deleted(session):
    """Avval yozuvlarni "Boshqa"ga o'tkazish kerak — baza buni majburlaydi."""
    user = await _user(session)
    custom = Category(user_id=user.id, name="Mashina")
    session.add(custom)
    await session.flush()
    session.add(_expense(user, custom))
    await session.flush()

    with pytest.raises(IntegrityError):
        await session.execute(delete(Category).where(Category.id == custom.id))


# ---------------------------------------------------------------------------
# user_keywords va kaskad o'chirish
# ---------------------------------------------------------------------------


async def test_user_keyword_unique_per_user(session):
    user = await _user(session)
    category = await _category(session)
    session.add(UserKeyword(user_id=user.id, keyword="yandex", category_id=category.id))
    await session.flush()
    session.add(UserKeyword(user_id=user.id, keyword="yandex", category_id=category.id))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_deleting_user_cascades(session):
    user = await _user(session)
    custom = Category(user_id=user.id, name="Mashina")
    session.add(custom)
    await session.flush()
    session.add_all(
        [
            _expense(user, custom),
            _income(user),
            UserKeyword(user_id=user.id, keyword="benzin", category_id=custom.id),
        ]
    )
    await session.commit()

    await session.execute(delete(User).where(User.id == user.id))
    await session.commit()

    for model in (Transaction, UserKeyword):
        assert await session.scalar(select(func.count()).select_from(model)) == 0
    # standart kategoriyalar joyida qoladi, faqat shaxsiysi o'chadi
    assert await session.scalar(select(func.count()).select_from(Category)) == 11
