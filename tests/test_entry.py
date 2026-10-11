"""Pipeline: to'liq matn -> Entry."""

from datetime import date

import pytest

from bot.db.models import TransactionType
from bot.services.entry import (
    AmountQuestion,
    Entry,
    EntryStatus,
    parse_entry,
    with_amount,
    with_category,
)

TODAY = date(2026, 10, 11)
YESTERDAY = date(2026, 10, 10)
EXPENSE, INCOME = TransactionType.EXPENSE, TransactionType.INCOME


@pytest.mark.parametrize(
    ("text", "kind", "amount", "day", "category"),
    [
        ("taksi 30000", EXPENSE, 30_000, TODAY, "Transport"),
        ("taksiga 30 ming", EXPENSE, 30_000, TODAY, "Transport"),
        ("такси 25к", EXPENSE, 25_000, TODAY, "Transport"),
        ("kecha taksi 25k", EXPENSE, 25_000, YESTERDAY, "Transport"),
        ("taksi 25k kecha", EXPENSE, 25_000, YESTERDAY, "Transport"),
        ("o'tgan kuni kino 40000", EXPENSE, 40_000, date(2026, 10, 9), "Ko'ngilochar"),
        ("non 15.300 5.10", EXPENSE, 15_300, date(2026, 10, 5), "Oziq-ovqat"),
        ("5-oktabr svet 80 ming", EXPENSE, 80_000, date(2026, 10, 5), "Uy/kommunal"),
        ("dorixona 45000 11.09", EXPENSE, 45_000, date(2026, 9, 11), "Sog'liq"),  # 30-kun
        ("+5 mln oylik", INCOME, 5_000_000, TODAY, None),
        ("+500000", INCOME, 500_000, TODAY, None),
        ("oylik keldi 4,5 mln", INCOME, 4_500_000, TODAY, None),
        ("kecha stipendiya 800k", INCOME, 800_000, YESTERDAY, None),
        ("+200k taksi", INCOME, 200_000, TODAY, None),  # kirimga kategoriya berilmaydi
    ],
)
def test_ready(text, kind, amount, day, category):
    entry = parse_entry(text, TODAY)
    assert entry.status is EntryStatus.READY
    assert (entry.kind, entry.amount, entry.occurred_on, entry.category) == (
        kind,
        amount,
        day,
        category,
    )
    assert entry.note == text


def test_kopek_rounded():
    entry = parse_entry("non 12500,50", TODAY)
    assert entry.status is EntryStatus.READY
    assert entry.amount == 12_501
    assert entry.rounded


@pytest.mark.parametrize("text", ["30000", "taksi non 20000", "nonushta 15000"])
def test_need_category(text):
    entry = parse_entry(text, TODAY)
    assert entry.status is EntryStatus.NEED_CATEGORY
    assert entry.amount is not None
    assert entry.category is None


@pytest.mark.parametrize(
    ("text", "question", "category"),
    [
        ("taksi", AmountQuestion.MISSING, "Transport"),
        ("kecha taksi", AmountQuestion.MISSING, "Transport"),
        ("2 ta non 5000", AmountQuestion.MULTIPLE, "Oziq-ovqat"),
        ("5.10 kecha", AmountQuestion.TWO_DATES, None),  # CLAUDE.md dagi ma'lum cheklov
        ("kecha 5.10 taksi", AmountQuestion.TWO_DATES, "Transport"),
    ],
)
def test_need_amount(text, question, category):
    entry = parse_entry(text, TODAY)
    assert entry.status is EntryStatus.NEED_AMOUNT
    assert entry.question is question
    assert entry.amount is None
    assert entry.category == category


@pytest.mark.parametrize("text", ["taksi 0", "taksi -5000", "taksi 2 mlrd"])
def test_bad_amount(text):
    entry = parse_entry(text, TODAY)
    assert entry.status is EntryStatus.BAD_AMOUNT
    assert entry.reason


@pytest.mark.parametrize(
    "text",
    [
        "taksi 30000 31.02",  # mavjud bo'lmagan sana
        "taksi 30000 05.09",  # 30 kundan eski
        "taksi 30000 12.10.2026",  # kelajak
    ],
)
def test_bad_date(text):
    entry = parse_entry(text, TODAY)
    assert entry.status is EntryStatus.BAD_DATE
    assert entry.reason


# ---------------------------------------------------------------------------
# Summa alohida yuborilganda
# ---------------------------------------------------------------------------


def test_with_amount_completes_known_category():
    pending = parse_entry("2 ta non 5000", TODAY)
    entry = with_amount(pending, "5000")
    assert entry.status is EntryStatus.READY
    assert (entry.amount, entry.category, entry.note) == (5_000, "Oziq-ovqat", "2 ta non 5000")
    assert entry.question is None


def test_with_amount_then_category_needed():
    entry = with_amount(parse_entry("5.10 kecha", TODAY), "30k")
    assert entry.status is EntryStatus.NEED_CATEGORY
    assert entry.amount == 30_000
    assert entry.occurred_on == YESTERDAY  # "kecha" ustun


def test_with_amount_income():
    entry = with_amount(parse_entry("oylik keldi", TODAY), "5 mln")
    assert entry.status is EntryStatus.READY
    assert (entry.kind, entry.amount) == (INCOME, 5_000_000)


def test_with_amount_invalid_keeps_waiting():
    entry = with_amount(parse_entry("taksi", TODAY), "0")
    assert entry.status is EntryStatus.BAD_AMOUNT
    assert entry.amount is None


@pytest.mark.parametrize("text", ["salom", "2 ta 5000"])
def test_with_amount_not_an_amount(text):
    assert with_amount(parse_entry("taksi", TODAY), text) is None


def test_with_category():
    entry = with_category(parse_entry("30000", TODAY), "Kiyim")
    assert entry.status is EntryStatus.READY
    assert entry.category == "Kiyim"


@pytest.mark.parametrize("text", ["taksi 30000", "5.10 kecha", "+5 mln oylik", "taksi"])
def test_dict_roundtrip(text):
    entry = parse_entry(text, TODAY)
    assert Entry.from_dict(entry.to_dict()) == entry
