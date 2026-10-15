"""AI bilan ishlash: so'rovni tuzish va javobni tekshirish. Provayderga bog'liq emas.

AI javobiga ishonilmaydi: kategoriya ruxsat etilgan ro'yxatda bo'lishi, summa esa
butun son va chegarada bo'lishi shart. Aks holda o'sha maydon None.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final, Protocol

from bot.services.parser import MAX_AMOUNT

MAX_INPUT_LEN: Final = 300  # uzun matn AI'ga to'liq yuborilmaydi

SYSTEM_PROMPT: Final = """\
Sen shaxsiy xarajatlar hisobi botining yordamchisisan.
Foydalanuvchi bitta xarajatni o'zbekcha (lotin yoki kirill) yoki ruscha yozadi.

category: ro'yxatdagi nomlardan aynan bittasi yoki null.
- Matn kategoriya tavsifiga aniq mos kelsagina nomni tanla.
- Hech biri aniq mos kelmasa yoki ishonching komil bo'lmasa — null. Eng yaqiniga majburan tiqma:
  noto'g'ri kategoriyadan null yaxshi, foydalanuvchi o'zi tanlaydi.
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


# Standart kategoriyalar tavsifi: nomning o'zi chegarani bildirmaydi ("Kiyim" — aksessuarmi?).
# Shaxsiy kategoriyalar faqat nomi bilan beriladi.
CATEGORY_HINTS: Final[dict[str, str]] = {
    "Oziq-ovqat": "do'kon va bozordan oziq-ovqat mahsulotlari, uyda tayyorlanadigan ovqat uchun",
    "Transport": "taksi, jamoat transporti, yoqilg'i, avtomobil va velosiped, poyezd, samolyot",
    "Uy/kommunal": "kommunal to'lovlar, ijara, ta'mir, uy-ro'zg'or buyumlari va texnikasi",
    "Aloqa/internet": "mobil aloqa, internet, telefon va uning aksessuarlari, onlayn xizmatlar",
    "Kiyim": "faqat kiyim-kechak va poyabzal",
    "Sog'liq": "dori, shifokor, tahlillar, tibbiy xizmatlar va buyumlar",
    "Ta'lim": "kurslar, o'qish to'lovi, kitoblar, o'quv qurollari, imtihonlar",
    "Ko'ngilochar": "kino, konsert, o'yinlar, obunalar, sport va dam olish mashg'ulotlari",
    "Kafe/restoran": "uydan tashqarida ovqatlanish: kafe, restoran, fastfud, choyxona, kofe",
    "Sovg'alar": "boshqa odamga olingan sovg'a, gul, to'y va tug'ilgan kun xarajatlari",
}


def build_prompt(text: str, categories: list[str]) -> str:
    lines = [
        f"- {name}: {CATEGORY_HINTS[name]}" if name in CATEGORY_HINTS else f"- {name}"
        for name in categories
    ]
    names = "\n".join(lines)
    return f"Kategoriyalar:\n{names}\n\nMatn: {text[:MAX_INPUT_LEN]}"


def build_schema(categories: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            # null — "ishonchsiz" (Gemini: type massivida "null")
            "category": {"type": ["string", "null"], "enum": [*categories, None]},
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
