"""AI baholash: ai_eval.csv dagi iboralarni haqiqiy modelga yuborib, aniqlikni o'lchaydi.

CI'ga kirmaydi (tarmoq va kalit kerak). Ishga tushirish:
    uv run python -m scripts.eval_ai                  # .env dagi AI_MODEL
    uv run python -m scripts.eval_ai gemini-3.8-flash # boshqa model bilan solishtirish

CSV: category bo'sh — model "unknown" qaytarishi kutiladi (masalan, "Boshqa" holatlari);
amount bo'sh — summa tekshirilmaydi (u parserdan keladi).
"""

from __future__ import annotations

import asyncio
import csv
import statistics
import sys
import time
from pathlib import Path

from bot.config import get_settings
from bot.services.ai import SYSTEM_PROMPT, build_prompt, build_schema, parse_answer
from bot.services.categories import DEFAULT_CATEGORIES, FALLBACK_CATEGORY
from bot.services.gemini import GeminiClient

DATASET = Path(__file__).with_name("ai_eval.csv")
CATEGORIES = [name for name, _ in DEFAULT_CATEGORIES if name != FALLBACK_CATEGORY]


async def main(model: str | None) -> None:
    settings = get_settings()
    if not settings.gemini_api_key or not settings.gemini_api_key.get_secret_value():
        sys.exit("GEMINI_API_KEY .env da yo'q")
    model = model or settings.ai_model
    client = GeminiClient(settings.gemini_api_key.get_secret_value(), model, settings.ai_timeout_s)

    rows = list(csv.DictReader(DATASET.open(encoding="utf-8")))
    cat_ok = amount_ok = amount_total = failed = 0
    latencies: list[float] = []
    tokens: list[int] = []

    for row in rows:
        expected_cat = row["category"] or None
        expected_amount = int(row["amount"]) if row["amount"] else None
        started = time.monotonic()
        try:
            reply = await client.complete(
                system=SYSTEM_PROMPT,
                prompt=build_prompt(row["text"], CATEGORIES),
                schema=build_schema(CATEGORIES),
            )
            answer = parse_answer(reply.text, CATEGORIES)
            tokens.append((reply.tokens_in or 0) + (reply.tokens_out or 0))
        except Exception as e:  # noqa: BLE001 — baholashda har qanday xato hisoblanadi
            answer = None
            print(f"  XATO {row['text']!r}: {e}")
        latencies.append(time.monotonic() - started)

        if answer is None:
            failed += 1
            continue
        mark = "✓" if answer.category == expected_cat else "✗"
        cat_ok += answer.category == expected_cat
        if expected_amount is not None:
            amount_total += 1
            amount_ok += answer.amount == expected_amount
            if answer.amount != expected_amount:
                mark += f" summa {answer.amount} (kutilgan {expected_amount})"
        if not mark.startswith("✓") or " " in mark:
            print(f"  {mark} {row['text']!r}: {answer.category} (kutilgan {expected_cat})")

    n = len(rows)
    print(f"\nModel: {model}, iboralar: {n}")
    print(f"Kategoriya aniqligi: {cat_ok}/{n} = {cat_ok / n:.0%}")
    if amount_total:
        print(f"Summa aniqligi: {amount_ok}/{amount_total} = {amount_ok / amount_total:.0%}")
    print(f"Xato/buzuq javob: {failed}")
    print(f"Kechikish: median {statistics.median(latencies):.2f} s, max {max(latencies):.2f} s")
    if tokens:
        print(f"Token (kirish+chiqish): o'rtacha {statistics.mean(tokens):.0f}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
