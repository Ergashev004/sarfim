"""Kalit so'zlar bo'yicha kategoriya va kirimni aniqlash (AI'siz).

Qoida: so'z o'zakdan boshlansa mos keladi ("taksiga" -> "taksi").
3 harfli va undan qisqa o'zaklar ("non", "gaz", "osh") faqat to'liq yoki ma'lum qo'shimcha
bilan mos keladi — aks holda "nonushta" non, "gazeta" gaz bo'lib qolardi.
"""

from __future__ import annotations

import re
from typing import Final

from bot.services.parser import normalize

SHORT_STEM_LEN: Final = 3

# Qisqa o'zaklardan keyin ruxsat etilgan qo'shimchalar (lotin va kirill)
_SUFFIXES: Final = frozenset(
    {
        "", "ga", "ka", "qa", "da", "dan", "ni", "ning", "lar", "larga", "lari", "im", "imga",
        "ing", "i", "si", "ta", "chi",
        "га", "ка", "қа", "да", "дан", "ни", "нинг", "лар", "ларга", "лари", "им", "имга",
        "инг", "и", "си", "та", "чи",
    }
)  # fmt: skip

KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    "Oziq-ovqat": (
        "non", "sut", "go'sht", "gosht", "bozor", "market", "korzinka", "makro", "havas",
        "meva", "sabzavot", "kartoshka", "piyoz", "guruch", "tuxum", "shakar",
        "produkt", "oziq", "qatiq", "yog'", "pishloq",
        "нон", "сут", "гўшт", "гушт", "бозор", "маркет", "корзинка", "макро", "мева",
        "сабзавот", "картошка", "пиёз", "гуруч", "тухум", "шакар", "продукт", "озиқ",
        "хлеб", "молоко", "мясо",
    ),
    "Transport": (
        "taksi", "taxi", "yandex", "metro", "avtobus", "benzin", "propan", "metan",
        "yo'lkira", "yolkira", "poyezd", "poezd", "samolyot", "parkovka", "mykar",
        "такси", "яндекс", "метро", "автобус", "бензин", "пропан", "метан", "йўлкира",
        "поезд", "самолёт", "самолет", "парковка",
    ),
    "Uy/kommunal": (
        "svet", "elektr", "gaz", "suv", "kommunal", "ijara", "kvartira", "kvartplata",
        "musor", "chiqindi", "remont", "ta'mir",
        "свет", "электр", "газ", "сув", "коммунал", "ижара", "квартира", "мусор", "ремонт",
    ),
    "Aloqa/internet": (
        "internet", "telefon", "mobil", "beeline", "ucell", "uzmobile", "mobiuz", "tarif",
        "wifi", "aloqa",
        "интернет", "телефон", "мобил", "билайн", "тариф", "алоқа",
    ),
    "Kiyim": (
        "kiyim", "ko'ylak", "koylak", "shim", "poyabzal", "poyafzal", "krossovka", "tufli",
        "kurtka", "futbolka", "palto", "paypoq", "jinsi", "etik",
        "кийим", "кўйлак", "куйлак", "шим", "пойабзал", "пойафзал", "кроссовка", "туфли",
        "куртка", "футболка", "пальто", "пайпоқ", "джинси",
    ),
    "Sog'liq": (
        "dori", "dorixona", "apteka", "shifokor", "vrach", "doktor", "klinika", "kasalxona",
        "stomatolog", "tish", "analiz",
        "дори", "дорихона", "аптека", "шифокор", "врач", "доктор", "клиника", "касалхона",
        "стоматолог", "тиш", "анализ",
    ),
    "Ta'lim": (
        "kurs", "kitob", "darslik", "kontrakt", "o'qish", "oqish", "repetitor", "ta'lim",
        "talim", "maktab", "universitet", "daftar", "udemy", "coursera",
        "курс", "китоб", "дарслик", "контракт", "ўқиш", "укиш", "репетитор", "таълим",
        "мактаб", "университет", "дафтар",
    ),
    "Ko'ngilochar": (
        "kino", "konsert", "teatr", "o'yin", "oyin", "playstation", "netflix", "spotify",
        "bouling", "boulling",
        "кино", "концерт", "театр", "ўйин", "уйин", "нетфликс",
    ),
    "Kafe/restoran": (
        "kafe", "cafe", "restoran", "kofe", "coffee", "choyxona", "oshxona", "fastfud",
        "fastfood", "lavash", "burger", "shaurma", "pizza", "pitsa", "evos", "kfc", "osh",
        "somsa", "samsa", "tushlik",
        "кафе", "ресторан", "кофе", "чойхона", "ошхона", "лаваш", "бургер", "шаурма",
        "пицца", "эвос", "ош", "сомса", "тушлик",
    ),
    "Sovg'alar": (
        "sovg'a", "sovga", "tug'ilgan", "tugilgan", "gul", "guldasta", "to'y", "toy", "tuhfa",
        "podarok",
        "совға", "совга", "туғилган", "тугилган", "гул", "тўй", "туй", "туҳфа", "подарок",
    ),
}  # fmt: skip

INCOME_KEYWORDS: Final = (
    "oylik", "oylig", "maosh", "stipendiya", "keldi", "kirim", "avans",
    "ойлик", "ойлиг", "маош", "стипендия", "келди", "кирим", "аванс",
)  # fmt: skip

_TOKEN_RE = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)*")


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(normalize(text))


def _matches(token: str, stem: str) -> bool:
    if not token.startswith(stem):
        return False
    if len(stem) > SHORT_STEM_LEN:
        return True
    return token[len(stem) :] in _SUFFIXES


def _any_match(tokens: list[str], stems: tuple[str, ...]) -> bool:
    return any(_matches(t, s) for t in tokens for s in stems)


def categorize(text: str) -> str | None:
    """Bitta kategoriya aniq topilsa uning nomi, topilmasa yoki bir nechta bo'lsa — None."""
    tokens = _tokens(text)
    found = [name for name, stems in KEYWORDS.items() if _any_match(tokens, stems)]
    return found[0] if len(found) == 1 else None


def is_income(text: str) -> bool:
    return normalize(text).startswith("+") or _any_match(_tokens(text), INCOME_KEYWORDS)
