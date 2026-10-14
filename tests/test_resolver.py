from datetime import date

import pytest
from sqlalchemy import select

from bot.db import repo
from bot.db.models import AiRequest, TransactionSource
from bot.services.ai import UNKNOWN
from bot.services.entry import AmountQuestion, EntryStatus, parse_entry
from bot.services.resolver import keyword_candidate, learn_keyword, resolve
from tests.fakes import gateway

TODAY = date(2026, 10, 11)


@pytest.fixture
async def user(session):
    u = await repo.get_or_create_user(session, 1001, "Akobir")
    await session.commit()
    return u


async def _cat_id(session, name):
    return (await repo.get_default_category(session, name)).id


async def _log(session) -> list[AiRequest]:
    return list(await session.scalars(select(AiRequest).order_by(AiRequest.id)))


# ---------------------------------------------------------------------------
# Kalit so'zni o'rganish
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("note", "word"),
    [
        ("nonushta 20000", "nonushta"),
        ("kecha velosiped 300 ming", "velosiped"),  # sana va "ming" o'tkaziladi
        ("Velosiped uchun 300000", "velosiped"),
        ("5.10 trenajor 50000 so'm", "trenajor"),
        ("ab 5000", None),  # juda qisqa
        ("50000", None),
    ],
)
def test_keyword_candidate(note, word):
    assert keyword_candidate(note, TODAY) == word


async def test_learn_keyword_upserts(session, user):
    sport = await _cat_id(session, "Ko'ngilochar")
    food = await _cat_id(session, "Oziq-ovqat")
    assert await learn_keyword(session, user.id, "nonushta 20000", sport, TODAY) == "nonushta"
    await learn_keyword(session, user.id, "nonushta 30000", food, TODAY)  # qayta tanlandi
    found = await repo.find_user_keyword_categories(session, user.id, ["nonushta"])
    assert [c.name for c in found] == ["Oziq-ovqat"]


async def test_fallback_category_not_learned(session, user):
    other = await _cat_id(session, "Boshqa")
    assert await learn_keyword(session, user.id, "nonushta 20000", other, TODAY) is None
    assert await repo.find_user_keyword_categories(session, user.id, ["nonushta"]) == []


async def test_foreign_category_not_learned(session, user):
    stranger = await repo.get_or_create_user(session, 2002, None)
    theirs = await repo.add_custom_category(session, stranger.id, "Baliq", None)
    assert await learn_keyword(session, user.id, "nonushta 20000", theirs.id, TODAY) is None


# ---------------------------------------------------------------------------
# NEED_CATEGORY: user_keywords -> AI
# ---------------------------------------------------------------------------


async def test_user_keyword_used_before_ai(session, user):
    await learn_keyword(session, user.id, "nonushta 1", await _cat_id(session, "Oziq-ovqat"), TODAY)
    ai, client = gateway()
    entry = await resolve(session, user.id, parse_entry("nonushta 20000", TODAY), TODAY, ai)
    assert entry.status is EntryStatus.READY
    assert (entry.category, entry.source) == ("Oziq-ovqat", TransactionSource.KEYWORD)
    assert client.calls == []


async def test_user_keywords_are_per_user(session, user):
    stranger = await repo.get_or_create_user(session, 2002, None)
    await learn_keyword(
        session, stranger.id, "nonushta 1", await _cat_id(session, "Oziq-ovqat"), TODAY
    )
    entry = await resolve(session, user.id, parse_entry("nonushta 20000", TODAY), TODAY, None)
    assert entry.status is EntryStatus.NEED_CATEGORY


async def test_conflicting_user_keywords_ignored(session, user):
    await learn_keyword(session, user.id, "nonushta 1", await _cat_id(session, "Oziq-ovqat"), TODAY)
    await learn_keyword(session, user.id, "velosiped 1", await _cat_id(session, "Transport"), TODAY)
    entry = parse_entry("nonushta velosiped 20000", TODAY)
    assert (await resolve(session, user.id, entry, TODAY, None)).status is EntryStatus.NEED_CATEGORY


async def test_ai_category_saved_with_ai_source(session, user):
    ai, client = gateway({"category": "Transport", "amount": 300000})
    entry = await resolve(session, user.id, parse_entry("velosiped 300000", TODAY), TODAY, ai)
    assert entry.status is EntryStatus.READY
    assert (entry.category, entry.source, entry.amount) == (
        "Transport",
        TransactionSource.AI,
        300000,
    )
    # AI'ga "Boshqa" berilmaydi, lekin shaxsiy kategoriyalar beriladi
    assert "Boshqa" not in client.calls[0]["schema"]["properties"]["category"]["enum"]
    [row] = await _log(session)
    assert (row.success, row.tokens_in, row.tokens_out, row.input_text) == (
        True, 120, 15, "velosiped 300000"
    )  # fmt: skip


async def test_ai_sees_custom_categories(session, user):
    await repo.add_custom_category(session, user.id, "Sport", "🏷")
    ai, client = gateway({"category": "Sport", "amount": 0})
    entry = await resolve(session, user.id, parse_entry("velosiped 300000", TODAY), TODAY, ai)
    assert entry.category == "Sport"
    assert "- Sport" in client.calls[0]["prompt"]


async def test_ai_amount_ignored_when_amount_known(session, user):
    ai, _ = gateway({"category": "Transport", "amount": 999})
    entry = await resolve(session, user.id, parse_entry("velosiped 300000", TODAY), TODAY, ai)
    assert entry.amount == 300000


@pytest.mark.parametrize(
    "reply",
    [
        {"category": UNKNOWN, "amount": 0},
        {"category": "Boshqa", "amount": 0},
        {"category": "Mashina", "amount": 0},  # ro'yxatda yo'q
        "buzuq javob",
        TimeoutError(),
        RuntimeError("503"),
    ],
)
async def test_ai_failure_falls_back_to_buttons(session, user, reply):
    ai, _ = gateway(reply)
    entry = await resolve(session, user.id, parse_entry("velosiped 300000", TODAY), TODAY, ai)
    assert entry.status is EntryStatus.NEED_CATEGORY
    assert entry.category is None
    [row] = await _log(session)
    assert row.latency_ms >= 0


async def test_ai_errors_logged_as_failed(session, user):
    ai, _ = gateway(RuntimeError("503"), "buzuq javob")
    for _ in range(2):
        await resolve(session, user.id, parse_entry("velosiped 300000", TODAY), TODAY, ai)
    rows = await _log(session)
    assert [(r.success, r.response) for r in rows] == [(False, None), (False, "buzuq javob")]


async def test_daily_limit(session, user):
    ai, client = gateway(*[{"category": "Transport", "amount": 0}] * 3, limit=2)
    statuses = []
    for _ in range(3):
        entry = await resolve(session, user.id, parse_entry("velosiped 300000", TODAY), TODAY, ai)
        statuses.append(entry.status)
    assert statuses == [EntryStatus.READY, EntryStatus.READY, EntryStatus.NEED_CATEGORY]
    assert len(client.calls) == 2


async def test_daily_limit_is_per_user(session, user):
    stranger = await repo.get_or_create_user(session, 2002, None)
    ai, client = gateway(*[{"category": "Transport", "amount": 0}] * 2, limit=1)
    for uid in (stranger.id, user.id):
        entry = await resolve(session, uid, parse_entry("velosiped 300000", TODAY), TODAY, ai)
        assert entry.status is EntryStatus.READY


async def test_without_ai_nothing_changes(session, user):
    entry = parse_entry("velosiped 300000", TODAY)
    assert await resolve(session, user.id, entry, TODAY, None) == entry
    assert await _log(session) == []


# ---------------------------------------------------------------------------
# Bir nechta raqam: AI summani taklif qiladi
# ---------------------------------------------------------------------------


async def test_multiple_numbers_need_confirmation(session, user):
    ai, _ = gateway({"category": "Transport", "amount": 10000})
    entry = parse_entry("2 ta velosiped 5000 dan", TODAY)
    assert entry.question is AmountQuestion.MULTIPLE
    entry = await resolve(session, user.id, entry, TODAY, ai)
    assert entry.status is EntryStatus.CONFIRM_AI
    assert (entry.amount, entry.category, entry.source) == (
        10000,
        "Transport",
        TransactionSource.AI,
    )


async def test_keyword_category_beats_ai(session, user):
    ai, _ = gateway({"category": "Transport", "amount": 5000})
    entry = await resolve(session, user.id, parse_entry("2 ta non 5000", TODAY), TODAY, ai)
    assert entry.status is EntryStatus.CONFIRM_AI
    assert (entry.category, entry.source) == ("Oziq-ovqat", TransactionSource.KEYWORD)


async def test_user_keyword_beats_ai_with_multiple_numbers(session, user):
    await learn_keyword(session, user.id, "velosiped 1", await _cat_id(session, "Kiyim"), TODAY)
    ai, _ = gateway({"category": "Transport", "amount": 5000})
    entry = await resolve(session, user.id, parse_entry("2 ta velosiped 5000", TODAY), TODAY, ai)
    assert (entry.category, entry.source) == ("Kiyim", TransactionSource.KEYWORD)


async def test_ai_amount_without_category(session, user):
    ai, _ = gateway({"category": UNKNOWN, "amount": 5000})
    entry = await resolve(session, user.id, parse_entry("2 ta velosiped 5000", TODAY), TODAY, ai)
    assert entry.status is EntryStatus.CONFIRM_AI
    assert entry.category is None


@pytest.mark.parametrize("reply", [{"category": "Transport", "amount": 0}, TimeoutError()])
async def test_no_ai_amount_asks_user(session, user, reply):
    ai, _ = gateway(reply)
    entry = await resolve(session, user.id, parse_entry("2 ta velosiped 5000", TODAY), TODAY, ai)
    assert entry.status is EntryStatus.NEED_AMOUNT
    assert entry.question is AmountQuestion.MULTIPLE


async def test_missing_amount_not_sent_to_ai(session, user):
    ai, client = gateway()
    entry = await resolve(session, user.id, parse_entry("velosiped", TODAY), TODAY, ai)
    assert entry.question is AmountQuestion.MISSING
    assert client.calls == []


async def test_income_with_multiple_numbers_has_no_category(session, user):
    ai, _ = gateway({"category": "Transport", "amount": 5000000})
    entry = await resolve(session, user.id, parse_entry("+ 2 oylik 5 mln", TODAY), TODAY, ai)
    assert entry.status is EntryStatus.CONFIRM_AI
    assert entry.category is None


# ---------------------------------------------------------------------------
# user_keywords lug'atdan ustun
# ---------------------------------------------------------------------------


async def test_user_keyword_beats_dictionary(session, user):
    entry = parse_entry("osh 30000", TODAY)
    assert entry.category == "Kafe/restoran"  # lug'at bo'yicha
    await learn_keyword(session, user.id, "osh 1", await _cat_id(session, "Oziq-ovqat"), TODAY)
    entry = await resolve(session, user.id, entry, TODAY, None)
    assert entry.status is EntryStatus.READY
    assert (entry.category, entry.source) == ("Oziq-ovqat", TransactionSource.KEYWORD)


async def test_latest_correction_wins(session, user):
    for name in ("Oziq-ovqat", "Sovg'alar", "Kafe/restoran", "Oziq-ovqat"):
        await learn_keyword(session, user.id, "osh 1", await _cat_id(session, name), TODAY)
        entry = await resolve(session, user.id, parse_entry("osh 30000", TODAY), TODAY, None)
        assert entry.category == name


async def test_user_keyword_overrides_dictionary_with_multiple_numbers(session, user):
    await learn_keyword(session, user.id, "non 1", await _cat_id(session, "Sovg'alar"), TODAY)
    ai, _ = gateway({"category": "Transport", "amount": 5000})
    entry = await resolve(session, user.id, parse_entry("2 ta non 5000", TODAY), TODAY, ai)
    assert entry.status is EntryStatus.CONFIRM_AI
    assert (entry.category, entry.source) == ("Sovg'alar", TransactionSource.KEYWORD)


async def test_user_keyword_kept_while_amount_asked(session, user):
    await learn_keyword(session, user.id, "osh 1", await _cat_id(session, "Oziq-ovqat"), TODAY)
    entry = await resolve(session, user.id, parse_entry("osh", TODAY), TODAY, None)
    assert entry.status is EntryStatus.NEED_AMOUNT
    assert entry.category == "Oziq-ovqat"


async def test_ambiguous_user_keywords_fall_back_to_dictionary(session, user):
    await learn_keyword(session, user.id, "osh 1", await _cat_id(session, "Oziq-ovqat"), TODAY)
    await learn_keyword(session, user.id, "palov 1", await _cat_id(session, "Transport"), TODAY)
    entry = await resolve(session, user.id, parse_entry("osh palov 30000", TODAY), TODAY, None)
    assert (entry.category, entry.source) == ("Kafe/restoran", TransactionSource.KEYWORD)


async def test_income_ignores_user_keywords(session, user):
    await learn_keyword(session, user.id, "oylik 1", await _cat_id(session, "Transport"), TODAY)
    entry = await resolve(session, user.id, parse_entry("oylik 5 mln", TODAY), TODAY, None)
    assert entry.category is None
