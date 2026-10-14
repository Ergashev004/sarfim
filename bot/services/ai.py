"""AI bilan ishlash: so'rovni tuzish va javobni tekshirish. Provayderga bog'liq emas.

AI javobiga ishonilmaydi: kategoriya ruxsat etilgan ro'yxatda bo'lishi, summa esa
butun son va chegarada bo'lishi shart. Aks holda o'sha maydon None.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final, Protocol

from bot.services.parser import MAX_AMOUNT

UNKNOWN: Final = "unknown"  # sxemada "topilmadi" uchun (null'dan ko'ra barqaror)
MAX_INPUT_LEN: Final = 300  # uzun matn AI'ga to'liq yuborilmaydi

SYSTEM_PROMPT: Final = """\
Sen shaxsiy xarajatlar hisobi botining yordamchisisan.
Foydalanuvchi bitta xarajatni o'zbekcha (lotin yoki kirill) yoki ruscha yozadi.

category: ro'yxatdagi nomlardan aynan bittasi. Ishonching komil bo'lmasa "unknown".
amount: xarajatning jami summasi so'mda, butun son. Aniqlab bo'lmasa 0.
- "2 ta non 5000" — yozilgan summa jami deb olinadi: 5000.
- "2 ta non 5000 dan", "5000 tadan", "donasi 5000" — bittasining narxi: 10000.
- "15 ming", "15k" = 15000; "1,5 mln" = 1500000.
- Sana, vaqt, telefon raqami, miqdor (dona, kg, litr) summa emas.
Faqat JSON qaytar."""


@dataclass(frozen=True)
class AiReply:
    """Provayderdan kelgan xom javob."""

    text: str
    tokens_in: int | None = None
    tokens_out: int | None = None


class AiClient(Protocol):
    async def complete(self, *, system: str, prompt: str, schema: dict) -> AiReply: ...


@dataclass(frozen=True)
class AiAnswer:
    category: str | None
    amount: int | None


def build_prompt(text: str, categories: list[str]) -> str:
    names = "\n".join(f"- {name}" for name in categories)
    return f"Kategoriyalar:\n{names}\n\nMatn: {text[:MAX_INPUT_LEN]}"


def build_schema(categories: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": [*categories, UNKNOWN]},
            "amount": {"type": "integer", "minimum": 0},
        },
        "required": ["category", "amount"],
    }


def parse_answer(raw: str, categories: list[str]) -> AiAnswer | None:
    """JSON buzuq bo'lsa None. Noto'g'ri maydon — shu maydon None."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    category = data.get("category")
    if category not in categories:
        category = None

    amount = data.get("amount")
    # bool ham int'ning vorisi — alohida rad etamiz; float hech qachon qabul qilinmaydi
    if isinstance(amount, bool) or not isinstance(amount, int) or not 0 < amount <= MAX_AMOUNT:
        amount = None

    return AiAnswer(category=category, amount=amount)
