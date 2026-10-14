"""Yozuv kategoriyasini aniqlashtirish: user_keywords (lug'atdan ustun) -> AI.

Telegram'ga bog'liq emas; bazaga faqat repo orqali murojaat qiladi va commit qilmaydi.
AI ishlamasa (xato, timeout, buzuq JSON, limit) yozuv o'zgarmay qaytadi — bot tugmalarni chiqaradi.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from datetime import time as dtime
from typing import Final
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import repo
from bot.db.models import TransactionSource, TransactionType
from bot.services.ai import (
    SYSTEM_PROMPT,
    AiAnswer,
    AiClient,
    build_prompt,
    build_schema,
    parse_answer,
)
from bot.services.categories import FALLBACK_CATEGORY
from bot.services.categorizer import tokens
from bot.services.entry import (
    AmountQuestion,
    Entry,
    EntryStatus,
    with_ai_amount,
    with_category,
    with_learned_category,
)
from bot.services.parser import parse_date

log = logging.getLogger(__name__)

MIN_KEYWORD_LEN: Final = 3
MAX_RESPONSE_LOG: Final = 2000
# Kategoriya hali kerak bo'ladigan holatlar (BAD_* va tasdiq kutilayotgan yozuvga tegilmaydi)
_CATEGORY_STATUSES: Final = frozenset(
    {EntryStatus.READY, EntryStatus.NEED_CATEGORY, EntryStatus.NEED_AMOUNT}
)

# Summa va bog'lovchi so'zlar kategoriya haqida hech narsa demaydi
_STOP_WORDS: Final = frozenset(
    {
        "so'm", "som", "sum", "ming", "mln", "mlrd", "million", "milliard", "uchun", "bilan",
        "сўм", "сум", "минг", "млн", "млрд", "учун", "билан", "тыс", "руб",
    }
)  # fmt: skip


@dataclass(frozen=True)
class AiGateway:
    """AI klienti va unga oid sozlamalar (handler'larga `ai` nomi bilan uzatiladi)."""

    client: AiClient
    daily_limit: int
    tz: ZoneInfo


def keyword_words(note: str, today: date) -> list[str]:
    """Matndagi kategoriyani bildirishi mumkin so'zlar (sana va summasiz)."""
    rest = parse_date(note, today).rest
    return [w for w in tokens(rest) if len(w) >= MIN_KEYWORD_LEN and w not in _STOP_WORDS]


def keyword_candidate(note: str, today: date) -> str | None:
    """Foydalanuvchi kategoriyani tanlaganda eslab qolinadigan so'z — birinchi mazmunli so'z."""
    words = keyword_words(note, today)
    return words[0] if words else None


async def learn_keyword(
    session: AsyncSession, user_id: int, note: str | None, category_id: int, today: date
) -> str | None:
    """Kategoriya qo'lda tanlanganda so'zni eslab qoladi. "Boshqa" o'rganilmaydi."""
    category = await repo.get_category(session, user_id, category_id)
    if category is None or category.name == FALLBACK_CATEGORY:
        return None
    word = keyword_candidate(note or "", today)
    if word is not None:
        await repo.save_user_keyword(session, user_id, word, category_id)
    return word


async def _from_user_keywords(
    session: AsyncSession, user_id: int, entry: Entry, today: date
) -> str | None:
    found = await repo.find_user_keyword_categories(
        session, user_id, keyword_words(entry.note, today)
    )
    return found[0].name if len(found) == 1 else None  # bir nechta bo'lsa — noaniq


async def _ai_categories(session: AsyncSession, user_id: int) -> list[str]:
    # "Boshqa" AI'ga berilmaydi: noaniq bo'lsa foydalanuvchi o'zi tanlagani yaxshi
    categories = await repo.list_categories(session, user_id)
    return [c.name for c in categories if c.name != FALLBACK_CATEGORY]


def _day_start_utc(today: date, tz: ZoneInfo) -> datetime:
    local = datetime.combine(today, dtime(), tz)
    return local.astimezone(UTC).replace(tzinfo=None)


async def ask_ai(
    session: AsyncSession, user_id: int, text: str, ai: AiGateway, today: date
) -> AiAnswer | None:
    """AI'dan so'raydi va ai_requests ga yozadi. Har qanday xatoda None, bot yiqilmaydi."""
    used = await repo.count_ai_requests_since(session, user_id, _day_start_utc(today, ai.tz))
    if used >= ai.daily_limit:
        log.info("AI kunlik limiti tugadi: user_id=%s", user_id)
        return None

    categories = await _ai_categories(session, user_id)
    started = time.monotonic()
    reply = None
    answer = None
    try:
        reply = await ai.client.complete(
            system=SYSTEM_PROMPT,
            prompt=build_prompt(text, categories),
            schema=build_schema(categories),
        )
        answer = parse_answer(reply.text, categories)
    except Exception:
        log.exception("AI so'rovi muvaffaqiyatsiz: user_id=%s", user_id)

    await repo.log_ai_request(
        session,
        user_id=user_id,
        input_text=text,
        response=reply.text[:MAX_RESPONSE_LOG] if reply else None,
        tokens_in=reply.tokens_in if reply else None,
        tokens_out=reply.tokens_out if reply else None,
        latency_ms=int((time.monotonic() - started) * 1000),
        success=answer is not None,
    )
    return answer


async def resolve(
    session: AsyncSession, user_id: int, entry: Entry, today: date, ai: AiGateway | None
) -> Entry:
    """Kategoriya tartibi: user_keywords -> lug'at (parse_entry topgani) -> AI -> tugmalar.

    Bir nechta raqam bo'lsa AI summani taklif qiladi (tasdiqlanadi).
    """
    if entry.kind is TransactionType.EXPENSE and entry.status in _CATEGORY_STATUSES:
        learned = await _from_user_keywords(session, user_id, entry, today)
        if learned is not None:
            entry = with_learned_category(entry, learned)

    if entry.status is EntryStatus.NEED_CATEGORY:
        if ai is None:
            return entry
        answer = await ask_ai(session, user_id, entry.note, ai, today)
        if answer is not None and answer.category is not None:
            return with_category(entry, answer.category, TransactionSource.AI)
        return entry

    if (
        entry.status is EntryStatus.NEED_AMOUNT
        and entry.question is AmountQuestion.MULTIPLE
        and ai is not None
    ):
        answer = await ask_ai(session, user_id, entry.note, ai, today)
        if answer is None or answer.amount is None:
            return entry
        # Kategoriya allaqachon bor (user_keywords yoki lug'at) bo'lsa, AI'niki olinmaydi
        category = None
        if entry.kind is TransactionType.EXPENSE and entry.category is None:
            category = answer.category
        return with_ai_amount(entry, answer.amount, category)

    return entry
