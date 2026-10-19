"""Hisobot so'rovlari haqiqiy migratsiyalangan SQLite bazada."""

from datetime import date

import pytest

from bot.db import repo
from bot.db.models import Category, TransactionSource, TransactionType
from bot.services.report import Granularity

START, END = date(2026, 10, 1), date(2026, 10, 16)


@pytest.fixture
async def cats(session) -> dict[str, Category]:
    names = ["Transport", "Oziq-ovqat", "Kafe/restoran", "Boshqa"]
    return {n: await repo.get_default_category(session, n) for n in names}


async def _expense(session, user, amount, category, day=date(2026, 10, 10)):
    return await repo.add_transaction(
        session,
        user_id=user.id,
        kind=TransactionType.EXPENSE,
        amount=amount,
        occurred_on=day,
        source=TransactionSource.KEYWORD,
        category_id=category.id,
    )


async def _income(session, user, amount, day=date(2026, 10, 10)):
    return await repo.add_transaction(
        session,
        user_id=user.id,
        kind=TransactionType.INCOME,
        amount=amount,
        occurred_on=day,
        source=TransactionSource.KEYWORD,
    )


# ---------------------------------------------------------------------------
# Jami
# ---------------------------------------------------------------------------


async def test_period_totals(session, me, cats):
    await _income(session, me, 5_000_000)
    await _expense(session, me, 30_000, cats["Transport"])
    await _expense(session, me, 90_000, cats["Oziq-ovqat"])
    assert await repo.period_totals(session, me.id, START, END) == (5_000_000, 120_000)


async def test_period_totals_empty(session, me):
    totals = await repo.period_totals(session, me.id, START, END)
    assert totals == (0, 0)
    assert all(isinstance(x, int) for x in totals)


async def test_period_bounds_are_inclusive(session, me, cats):
    for day, amount in [
        (date(2026, 9, 30), 1),  # chegaradan oldin
        (START, 10),
        (END, 100),
        (date(2026, 10, 17), 1000),  # chegaradan keyin
    ]:
        await _expense(session, me, amount, cats["Transport"], day)
    assert await repo.period_totals(session, me.id, START, END) == (0, 110)


async def test_reports_ignore_other_users(session, me, stranger, cats):
    await _expense(session, me, 10_000, cats["Transport"])
    await _income(session, stranger, 9_000_000)
    await _expense(session, stranger, 777_000, cats["Transport"])
    await _expense(session, stranger, 555_000, cats["Kafe/restoran"])

    assert await repo.period_totals(session, me.id, START, END) == (0, 10_000)
    assert await repo.expense_by_category(session, me.id, START, END) == [
        ("Transport", "🚕", 10_000, 1)
    ]
    assert await repo.expense_by_bucket(session, me.id, START, END, Granularity.DAY) == [
        (date(2026, 10, 10), 10_000)
    ]
    assert [tx.amount for tx, _ in await repo.last_transactions(session, me.id)] == [10_000]


# ---------------------------------------------------------------------------
# Kategoriyalar bo'yicha
# ---------------------------------------------------------------------------


async def test_expense_by_category_sorted_desc(session, me, cats):
    await _income(session, me, 5_000_000)  # kirim kategoriyalarga kirmaydi
    await _expense(session, me, 30_000, cats["Transport"])
    await _expense(session, me, 20_000, cats["Transport"])
    await _expense(session, me, 600_000, cats["Kafe/restoran"])
    await _expense(session, me, 90_000, cats["Oziq-ovqat"])

    rows = await repo.expense_by_category(session, me.id, START, END)
    assert [(name, amount, count) for name, _, amount, count in rows] == [
        ("Kafe/restoran", 600_000, 1),
        ("Oziq-ovqat", 90_000, 1),
        ("Transport", 50_000, 2),
    ]


async def test_expense_by_category_income_only(session, me):
    await _income(session, me, 5_000_000)
    assert await repo.expense_by_category(session, me.id, START, END) == []
    assert await repo.period_totals(session, me.id, START, END) == (5_000_000, 0)


async def test_deleted_custom_category_shows_as_boshqa(session, me, cats):
    car = await repo.add_custom_category(session, me.id, "Moshina", "🚗")
    await _expense(session, me, 500_000, car)
    await _expense(session, me, 60_000, cats["Boshqa"])
    assert (await repo.expense_by_category(session, me.id, START, END))[0][0] == "Moshina"

    await repo.delete_custom_category(session, me.id, car.id, cats["Boshqa"].id)
    rows = await repo.expense_by_category(session, me.id, START, END)
    assert [(name, amount, count) for name, _, amount, count in rows] == [("Boshqa", 560_000, 2)]


# ---------------------------------------------------------------------------
# Vaqt bo'yicha guruhlash
# ---------------------------------------------------------------------------


async def test_bucket_by_day(session, me, cats):
    await _expense(session, me, 100, cats["Transport"], date(2026, 10, 3))
    await _expense(session, me, 200, cats["Oziq-ovqat"], date(2026, 10, 3))
    await _expense(session, me, 50, cats["Transport"], date(2026, 10, 5))
    await _income(session, me, 9_999, date(2026, 10, 5))  # kirim grafikka kirmaydi

    assert await repo.expense_by_bucket(session, me.id, START, END, Granularity.DAY) == [
        (date(2026, 10, 3), 300),
        (date(2026, 10, 5), 50),
    ]


@pytest.mark.parametrize(
    ("day", "monday"),
    [
        (date(2026, 10, 12), date(2026, 10, 12)),  # dushanba — o'zi
        (date(2026, 10, 13), date(2026, 10, 12)),  # seshanba
        (date(2026, 10, 18), date(2026, 10, 12)),  # yakshanba — o'tgan dushanba
        (date(2026, 10, 19), date(2026, 10, 19)),  # keyingi dushanba
        (date(2027, 1, 3), date(2026, 12, 28)),  # yakshanba, yil almashishi
    ],
)
async def test_bucket_week_starts_on_monday(session, me, cats, day, monday):
    await _expense(session, me, 100, cats["Transport"], day)
    rows = await repo.expense_by_bucket(session, me.id, day, day, Granularity.WEEK)
    assert rows == [(monday, 100)]


async def test_bucket_week_sunday_and_monday_split(session, me, cats):
    await _expense(session, me, 100, cats["Transport"], date(2026, 10, 18))  # yakshanba
    await _expense(session, me, 200, cats["Transport"], date(2026, 10, 19))  # dushanba
    start, end = date(2026, 10, 12), date(2026, 10, 25)
    assert await repo.expense_by_bucket(session, me.id, start, end, Granularity.WEEK) == [
        (date(2026, 10, 12), 100),
        (date(2026, 10, 19), 200),
    ]


async def test_bucket_by_month(session, me, cats):
    await _expense(session, me, 100, cats["Transport"], date(2026, 8, 31))
    await _expense(session, me, 200, cats["Transport"], date(2026, 9, 1))
    await _expense(session, me, 300, cats["Transport"], date(2026, 9, 30))
    await _expense(session, me, 400, cats["Transport"], date(2026, 10, 16))
    start, end = date(2026, 8, 1), date(2026, 10, 16)
    assert await repo.expense_by_bucket(session, me.id, start, end, Granularity.MONTH) == [
        (date(2026, 8, 1), 100),
        (date(2026, 9, 1), 500),
        (date(2026, 10, 1), 400),
    ]


async def test_large_sums_stay_int(session, me, cats):
    for _ in range(5):
        await _expense(session, me, 1_000_000_000, cats["Transport"])
    _, expense = await repo.period_totals(session, me.id, START, END)
    ((_, total),) = await repo.expense_by_bucket(session, me.id, START, END, Granularity.MONTH)
    assert expense == total == 5_000_000_000
    assert isinstance(expense, int)


# ---------------------------------------------------------------------------
# Oxirgi yozuvlar
# ---------------------------------------------------------------------------


async def test_last_transactions_newest_first_with_limit(session, me, cats):
    for amount in range(1, 13):
        await _expense(session, me, amount * 1000, cats["Transport"])
    await _income(session, me, 99_000)

    rows = await repo.last_transactions(session, me.id)
    assert len(rows) == 10
    assert rows[0][0].amount == 99_000 and rows[0][1] is None  # kirim — kategoriyasiz
    assert [tx.amount for tx, _ in rows[1:]] == [
        12_000,
        11_000,
        10_000,
        9_000,
        8_000,
        7_000,
        6_000,
        5_000,
        4_000,
    ]
    assert rows[1][1].name == "Transport"


async def test_last_transactions_order_by_entry_not_date(session, me, cats):
    await _expense(session, me, 1000, cats["Transport"], date(2026, 10, 15))
    await _expense(session, me, 2000, cats["Transport"], date(2026, 10, 1))  # keyin kiritildi
    rows = await repo.last_transactions(session, me.id, limit=5)
    assert [tx.amount for tx, _ in rows] == [2000, 1000]
