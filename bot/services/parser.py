"""Matndan summa va sanani ajratib olish.

Bu modul Telegram'ga ham, bazaga ham bog'liq emas: faqat matn kiradi, natija chiqadi.
`today` har doim tashqaridan beriladi, shuning uchun testlar soatga bog'liq bo'lmaydi.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

MAX_AMOUNT = 1_000_000_000  # 1 mlrd so'm
DATE_WINDOW_DAYS = 30  # bugundan orqaga necha kungacha ruxsat

# ---------------------------------------------------------------------------
# Matnni tozalash
# ---------------------------------------------------------------------------

_APOSTROPHES = str.maketrans({"ʻ": "'", "ʼ": "'", "’": "'", "‘": "'", "`": "'"})


def normalize(text: str) -> str:
    """Kichik harf, apostroflarni bir xil qilish, ortiqcha bo'shliqlarni olib tashlash."""
    text = text.translate(_APOSTROPHES).lower()
    text = text.replace(" ", " ")  # bank SMS'laridagi "qattiq" bo'shliq
    return re.sub(r"[ \t]+", " ", text).strip()


# ---------------------------------------------------------------------------
# Summa
# ---------------------------------------------------------------------------


class AmountStatus(StrEnum):
    OK = "ok"
    MISSING = "missing"  # matnda raqam yo'q -> summani so'raymiz
    MULTIPLE = "multiple"  # bir nechta raqam -> AI'ga yuboramiz
    INVALID = "invalid"  # 0, manfiy yoki 1 mlrd dan katta


@dataclass(frozen=True)
class AmountResult:
    status: AmountStatus
    value: int | None = None
    reason: str | None = None
    rounded: bool = False  # tiyin yaxlitlangan bo'lsa True (kartada ko'rsatish uchun)


_MULTIPLIERS: list[tuple[str, int]] = [
    (r"mlrd\w*|млрд\w*|milliard\w*", 1_000_000_000),
    (r"mln\w*|млн\w*|million\w*|millon\w*", 1_000_000),
    (r"ming\w*|минг\w*|тыс\w*", 1_000),
    (r"k\b|к\b", 1_000),
]
_MULT_RE = "|".join(f"(?:{p})" for p, _ in _MULTIPLIERS)

# Raqam: "30000", "30 000", "1.500.000", "1,5", "15300,50"
_NUMBER = r"\d+(?:[ .,]\d{3})*(?:[.,]\d{1,2})?(?!\d)"
_AMOUNT_RE = re.compile(
    rf"(?P<sign>(?:^|(?<=\s))-)?(?<![\d.,])(?P<num>{_NUMBER})(?:\s*(?P<mult>{_MULT_RE}))?",
    re.IGNORECASE,
)


def _multiplier_value(word: str) -> int:
    for pattern, value in _MULTIPLIERS:
        if re.fullmatch(pattern, word, re.IGNORECASE):
            return value
    raise ValueError(word)  # pragma: no cover - regex buni oldini oladi


def _to_decimal(token: str, has_multiplier: bool) -> Decimal:
    """'1.500.000' -> 1500000, '1,5' + mln -> 1.5, '15300,50' -> 15300.50.

    Qoida: ko'paytiruvchi bo'lsa, yagona ajratgich - kasr belgisi.
    Ko'paytiruvchi bo'lmasa, ajratgichdan keyin 3 ta raqam - minglik,
    1-2 ta raqam - kasr (tiyin).
    """
    groups = re.split(r"[ .,]", token)
    if len(groups) == 1:
        return Decimal(token)
    if has_multiplier and len(groups) == 2:
        return Decimal(f"{groups[0]}.{groups[1]}")
    if len(groups[-1]) in (1, 2):
        return Decimal(f"{''.join(groups[:-1])}.{groups[-1]}")
    return Decimal("".join(groups))


def _find_numbers(text: str) -> list[tuple[re.Match[str], Decimal]]:
    found = []
    for m in _AMOUNT_RE.finditer(text):
        mult_word = m.group("mult")
        value = _to_decimal(m.group("num"), has_multiplier=bool(mult_word))
        if mult_word:
            value *= _multiplier_value(mult_word)
        found.append((m, value))
    return found


def _merge_compound(items: list[tuple[re.Match[str], Decimal]]) -> list[tuple[bool, Decimal]]:
    """'15 ming 300' va '1 mln 200 ming' kabi qo'shma summalarni bitta songa birlashtiradi.

    Natija: (manfiymi, qiymat) ro'yxati.
    """
    merged: list[tuple[bool, Decimal]] = []
    prev_mult: int | None = None
    for m, value in items:
        mult_word = m.group("mult")
        mult = _multiplier_value(mult_word) if mult_word else 1
        # Oldingi bo'lak kattaroq ko'paytiruvchili bo'lsa va bu bo'lak undan kichik bo'lsa,
        # ular bitta summa: "15 ming" + "300"
        if merged and prev_mult and mult < prev_mult and value < prev_mult:
            negative, total = merged[-1]
            merged[-1] = (negative, total + value)
        else:
            merged.append((bool(m.group("sign")), value))
        prev_mult = mult if mult > 1 else None
    return merged


def parse_amount(text: str) -> AmountResult:
    text = normalize(text).lstrip("+").strip()
    numbers = _merge_compound(_find_numbers(text))

    if not numbers:
        return AmountResult(AmountStatus.MISSING)
    if len(numbers) > 1:
        return AmountResult(AmountStatus.MULTIPLE)

    negative, value = numbers[0]
    rounded_value = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    amount = int(rounded_value)

    if negative:
        return AmountResult(AmountStatus.INVALID, reason="Summa manfiy bo'lishi mumkin emas")
    if amount <= 0:
        return AmountResult(AmountStatus.INVALID, reason="Summa 0 dan katta bo'lishi kerak")
    if amount > MAX_AMOUNT:
        return AmountResult(AmountStatus.INVALID, reason="Summa 1 mlrd so'mdan oshmasligi kerak")
    return AmountResult(AmountStatus.OK, value=amount, rounded=rounded_value != value)


# ---------------------------------------------------------------------------
# Sana
# ---------------------------------------------------------------------------


class DateStatus(StrEnum):
    OK = "ok"
    NOT_FOUND = "not_found"  # sana yozilmagan -> bugun
    INVALID = "invalid"  # 31.02 kabi mavjud bo'lmagan sana
    FUTURE = "future"
    TOO_OLD = "too_old"


@dataclass(frozen=True)
class DateResult:
    status: DateStatus
    value: date | None
    rest: str  # sana olib tashlangan matn (summa parseri shu bilan ishlaydi)


_MONTHS = {
    "yanvar": 1,
    "fevral": 2,
    "mart": 3,
    "aprel": 4,
    "may": 5,
    "iyun": 6,
    "iyul": 7,
    "avgust": 8,
    "sentabr": 9,
    "sentyabr": 9,
    "oktabr": 10,
    "oktyabr": 10,
    "noyabr": 11,
    "dekabr": 12,
}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))

_RELATIVE = [
    (re.compile(r"\b(?:o'tgan|avvalgi|oldingi) kuni?\b"), 2),
    (re.compile(r"\bkecha\w*"), 1),
    (re.compile(r"\bbugun\w*"), 0),
]
# "5-oktabr", "5 oktabrda", "5-oktyabr kuni"
_NAMED_RE = re.compile(rf"(?<!\d)(?P<d>\d{{1,2}})(?:-| )?(?P<m>{_MONTH_RE})\w*")
# "05.10", "5/10", "05.10.2026", "05.10.26"
_NUMERIC_RE = re.compile(
    r"(?<![\d.,])(?P<d>\d{1,2})[./](?P<m>\d{1,2})(?:[./](?P<y>\d{4}|\d{2}))?(?![\d,]|\.\d)"
    # "12.5k", "1.5 mln" - bu summa, sana emas
    rf"(?!\s*(?:{_MULT_RE}))",
    re.IGNORECASE,
)


def _cut(text: str, m: re.Match[str]) -> str:
    return normalize(text[: m.start()] + " " + text[m.end() :])


def resolve_date(day: int, month: int, year: int | None, today: date) -> date | None:
    """Yil yozilmagan bo'lsa: bugundan keyin chiqsa, o'tgan yil deb olinadi (3-yanvarda 28.12)."""
    try:
        if year is not None:
            return date(year, month, day)
        candidate = date(today.year, month, day)
        if candidate > today:
            candidate = date(today.year - 1, month, day)
        return candidate
    except ValueError:
        return None


@dataclass(frozen=True)
class DateMatch:
    day: int
    month: int  # tekshirilmagan: 1–12 dan tashqarida bo'lishi mumkin
    year: int | None
    start: int
    end: int


def _to_match(m: re.Match[str]) -> DateMatch:
    month = _MONTHS[m.group("m")] if m.re is _NAMED_RE else int(m.group("m"))
    year_str = m.groupdict().get("y")
    year = None
    if year_str:
        year = int(year_str) + (2000 if len(year_str) == 2 else 0)
    return DateMatch(int(m.group("d")), month, year, m.start(), m.end())


def find_dates(text: str) -> list[DateMatch]:
    """Normallashgan matndagi barcha aniq sanalar (nisbiy so'zlarsiz), chapdan o'ngga."""
    found = [_to_match(m) for m in _NAMED_RE.finditer(text)]
    for m in _NUMERIC_RE.finditer(text):
        if all(m.end() <= d.start or m.start() >= d.end for d in found):
            found.append(_to_match(m))
    return sorted(found, key=lambda d: d.start)


def _check_window(value: date, today: date) -> DateStatus:
    if value > today:
        return DateStatus.FUTURE
    if value < today - timedelta(days=DATE_WINDOW_DAYS):
        return DateStatus.TOO_OLD
    return DateStatus.OK


def parse_date(text: str, today: date) -> DateResult:
    text = normalize(text)

    for pattern, days_ago in _RELATIVE:
        m = pattern.search(text)
        if m:
            return DateResult(DateStatus.OK, today - timedelta(days=days_ago), _cut(text, m))

    m = _NAMED_RE.search(text) or _NUMERIC_RE.search(text)
    if not m:
        return DateResult(DateStatus.NOT_FOUND, today, text)

    found = _to_match(m)
    day, month, year = found.day, found.month, found.year

    if not 1 <= month <= 12:
        # "15.30" sana emas (30-oy yo'q) - matnga tegmaymiz, summa parseri ko'radi
        return DateResult(DateStatus.NOT_FOUND, today, text)

    value = resolve_date(day, month, year, today)
    rest = _cut(text, m)
    if value is None:
        return DateResult(DateStatus.INVALID, None, rest)
    status = _check_window(value, today)
    return DateResult(status, value if status is DateStatus.OK else None, rest)
