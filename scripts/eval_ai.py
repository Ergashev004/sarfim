"""AI baholash: ai_eval.csv dagi iboralarni haqiqiy modelga yuborib, aniqlikni o'lchaydi.

CI'ga kirmaydi (tarmoq va kalit kerak). Ishga tushirish:
    uv run python -m scripts.eval_ai                         # .env dagi AI_MODEL, 15 RPM
    uv run python -m scripts.eval_ai gemini-3.8-flash --rpm 10

CSV: category bo'sh — model null qaytarishi kutiladi (masalan, "Boshqa" holatlari);
amount bo'sh — summa tekshirilmaydi (u parserdan keladi).
Aniqlik faqat javob olingan iboralar bo'yicha; xatolar (429, timeout, buzuq JSON) alohida.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from bot.config import get_settings
from bot.services.ai import (
    SYSTEM_PROMPT,
    AiAnswer,
    AiClient,
    AiReply,
    build_prompt,
    build_schema,
    parse_answer,
)
from bot.services.categories import DEFAULT_CATEGORIES, FALLBACK_CATEGORY
from bot.services.gemini import GeminiClient, is_rate_limited, retry_delay_s

DATASET = Path(__file__).with_name("ai_eval.csv")
CATEGORIES = [name for name, _ in DEFAULT_CATEGORIES if name != FALLBACK_CATEGORY]
MAX_RETRIES = 3
FALLBACK_DELAY_S = 30.0  # 429 da retryDelay bo'lmasa
ERROR_TEXT_LEN = 120


class Throttle:
    """So'rovlar orasida kamida 60/rpm soniya (qayta urinishlar ham hisobga kiradi)."""

    def __init__(self, rpm: int) -> None:
        self.interval = 60.0 / rpm
        self._last = float("-inf")

    async def wait(self) -> None:
        delay = self._last + self.interval - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        self._last = time.monotonic()


async def complete_with_retry(
    client: AiClient, throttle: Throttle, *, system: str, prompt: str, schema: dict
) -> tuple[AiReply, float]:
    """429 kelsa retryDelay qadar kutib, ko'pi bilan MAX_RETRIES marta qayta uriniladi.

    Kechikish — faqat muvaffaqiyatli API chaqiruvining o'zi (throttle va 429 kutishlarisiz).
    """
    for attempt in range(MAX_RETRIES + 1):
        await throttle.wait()
        started = time.monotonic()
        try:
            reply = await client.complete(system=system, prompt=prompt, schema=schema)
        except Exception as e:
            if not is_rate_limited(e) or attempt == MAX_RETRIES:
                raise
            delay = retry_delay_s(e) or FALLBACK_DELAY_S
            print(f"  429: {delay:.0f} s kutiladi (urinish {attempt + 1}/{MAX_RETRIES})")
            await asyncio.sleep(delay)
            continue
        return reply, time.monotonic() - started
    raise AssertionError("unreachable")


def short(error: BaseException) -> str:
    text = f"{type(error).__name__}: {error}".replace("\n", " ")
    return text[:ERROR_TEXT_LEN]


@dataclass
class Stats:
    total: int = 0
    answered: int = 0
    cat_ok: int = 0
    amount_checked: int = 0
    amount_ok: int = 0
    errors: list[str] = field(default_factory=list)
    latencies: list[float] = field(default_factory=list)
    tokens: list[int] = field(default_factory=list)


def score(stats: Stats, row: dict, answer: AiAnswer, raw: str) -> None:
    expected_cat = row["category"] or None
    expected_amount = int(row["amount"]) if row["amount"] else None
    stats.answered += 1
    problems = []
    if answer.category == expected_cat:
        stats.cat_ok += 1
    else:
        problems.append(f"kategoriya {answer.category} (kutilgan {expected_cat})")
    if expected_amount is not None:
        stats.amount_checked += 1
        if answer.amount == expected_amount:
            stats.amount_ok += 1
        else:
            problems.append(f"summa {answer.amount} (kutilgan {expected_amount})")
    if problems:
        print(f"  ✗ {row['text']!r}: {'; '.join(problems)} | javob: {raw[:ERROR_TEXT_LEN]}")


def report(stats: Stats, model: str) -> None:
    def pct(ok: int, n: int) -> str:
        return f"{ok}/{n} = {ok / n:.0%}" if n else "—"

    print(f"\nModel: {model}, iboralar: {stats.total}, javob olindi: {stats.answered}")
    print(f"Kategoriya aniqligi: {pct(stats.cat_ok, stats.answered)}")
    print(f"Summa aniqligi: {pct(stats.amount_ok, stats.amount_checked)}")
    print(f"Xatolar: {len(stats.errors)}")
    for err in stats.errors:
        print(f"  - {err}")
    if stats.latencies:
        print(
            f"Kechikish: median {statistics.median(stats.latencies):.2f} s, "
            f"max {max(stats.latencies):.2f} s"
        )
    if stats.tokens:
        print(f"Token (kirish+chiqish): o'rtacha {statistics.mean(stats.tokens):.0f}")


async def run(client: AiClient, model: str, rpm: int) -> Stats:
    rows = list(csv.DictReader(DATASET.open(encoding="utf-8")))
    stats = Stats(total=len(rows))
    throttle = Throttle(rpm)
    schema = build_schema(CATEGORIES)

    for row in rows:
        try:
            reply, latency = await complete_with_retry(
                client,
                throttle,
                system=SYSTEM_PROMPT,
                prompt=build_prompt(row["text"], CATEGORIES),
                schema=schema,
            )
        except Exception as e:  # noqa: BLE001 — baholashda har qanday xato hisoblanadi
            stats.errors.append(f"{row['text']!r}: {short(e)}")
            continue
        stats.latencies.append(latency)
        stats.tokens.append((reply.tokens_in or 0) + (reply.tokens_out or 0))

        answer = parse_answer(reply.text, CATEGORIES)
        if answer is None:
            stats.errors.append(f"{row['text']!r}: buzuq JSON: {reply.text[:ERROR_TEXT_LEN]}")
            continue
        score(stats, row, answer, reply.text)

    report(stats, model)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="AI kategoriya/summa aniqligini o'lchash")
    parser.add_argument("model", nargs="?", help="standart: .env dagi AI_MODEL")
    parser.add_argument("--rpm", type=int, default=15, help="daqiqasiga so'rovlar (free tier: 15)")
    args = parser.parse_args()
    if args.rpm <= 0:
        parser.error("--rpm musbat bo'lsin")

    settings = get_settings()
    key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else ""
    if not key:
        sys.exit("GEMINI_API_KEY .env da yo'q")
    model = args.model or settings.ai_model
    client = GeminiClient(key, model, settings.ai_timeout_s)
    asyncio.run(run(client, model, args.rpm))


if __name__ == "__main__":
    main()
