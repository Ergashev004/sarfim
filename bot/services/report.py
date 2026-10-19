"""Hisobot: davrlar, oraliqni o'qish va matn. Telegram'ga ham, bazaga ham bog'liq emas.

Yig'indilarni SQL hisoblaydi (repo), bu modul faqat davrni aniqlaydi va natijani yozadi.
`today` har doim tashqaridan beriladi.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from html import escape

from bot.services.card import category_label, format_amount
from bot.services.parser import DateMatch, find_dates, normalize, resolve_date

MAX_RANGE_DAYS = 366
CAPTION_LIMIT = 1024  # Telegram: rasm izohi, teglarsiz, UTF-16 birliklarida

# ---------------------------------------------------------------------------
# Davrlar
# ---------------------------------------------------------------------------


class PeriodKind(StrEnum):
    TODAY = "today"
    WEEK = "week"
    MONTH = "month"
    MONTHS_3 = "m3"
    MONTHS_6 = "m6"
    YEAR = "year"
    CUSTOM = "custom"


# Joriy oy bilan birga necha kalendar oy
_MONTH_SPANS = {
    PeriodKind.MONTH: 1,
    PeriodKind.MONTHS_3: 3,
    PeriodKind.MONTHS_6: 6,
    PeriodKind.YEAR: 12,
}


@dataclass(frozen=True)
class Period:
    kind: PeriodKind
    start: date
    end: date  # ikkala chegara ham kiradi

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def add_months(value: date, months: int) -> date:
    """Oy qo'shish; kun oy oxiridan oshsa oxirgi kunga qisqartiriladi (31.10 − 1 oy = 30.09)."""
    index = value.year * 12 + value.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def period_for(kind: PeriodKind, today: date) -> Period:
    if kind is PeriodKind.TODAY:
        return Period(kind, today, today)
    if kind is PeriodKind.WEEK:
        return Period(kind, today - timedelta(days=today.weekday()), today)
    if kind in _MONTH_SPANS:
        start = add_months(today.replace(day=1), -(_MONTH_SPANS[kind] - 1))
        return Period(kind, start, today)
    raise ValueError(f"{kind} uchun oraliq parse_range orqali olinadi")


def previous(period: Period) -> Period:
    """Taqqoslash uchun oldingi xuddi shunday davr (bir xil "bosqichda")."""
    if period.kind in _MONTH_SPANS:
        shift = -_MONTH_SPANS[period.kind]
        return Period(period.kind, add_months(period.start, shift), add_months(period.end, shift))
    if period.kind is PeriodKind.WEEK:
        week = timedelta(days=7)
        return Period(period.kind, period.start - week, period.end - week)
    # Bugun va ixtiyoriy oraliq: shuncha kun, darhol oldidan
    end = period.start - timedelta(days=1)
    return Period(period.kind, end - timedelta(days=period.days - 1), end)


# ---------------------------------------------------------------------------
# Ixtiyoriy oraliq
# ---------------------------------------------------------------------------


class RangeStatus(StrEnum):
    OK = "ok"
    NO_DATES = "no_dates"  # matnda sana yo'q — oraliq emas, oddiy yozuv bo'lishi mumkin
    BAD_FORMAT = "bad_format"
    INVALID = "invalid"  # 31.02 kabi
    FUTURE = "future"
    REVERSED = "reversed"
    TOO_LONG = "too_long"


@dataclass(frozen=True)
class RangeResult:
    status: RangeStatus
    period: Period | None = None


# Sanalardan tashqari matnda faqat ajratgichlar qolishi mumkin
_RANGE_FILLER_RE = re.compile(r"(?:[\s\-–—.,]|\bdan\b|\bgacha\b)*")


def _clamp_to_today(first: DateMatch, last: DateMatch, today: date) -> tuple[date, date] | None:
    """Boshlanish o'tgan, tugash kelajakda (yilsiz — joriy yil bo'yicha): tugash bugungacha."""
    start = resolve_date(first.day, first.month, first.year or today.year, today)
    end = resolve_date(last.day, last.month, last.year or today.year, today)
    if start is None or end is None or not start <= today < end:
        return None
    return start, today


def parse_range(text: str, today: date) -> RangeResult:
    """ "1.09 - 15.10", "01.09.2026 – 15.10.2026", "1 sentabr - 15 oktabr", yoki bitta sana.

    Boshlanish o'tgan, tugash kelajakda bo'lsa — tugash bugungacha qisqaradi (10.10-20.10 →
    10.10–bugun). Aks holda: yilsiz oxirgi sana bugundan, yilsiz boshlang'ich sana oxirgi
    sanadan keyin chiqsa — o'tgan yil deb olinadi (ikkalasi kelajakda; 20.12 - 10.01).
    """
    text = normalize(text)
    found = find_dates(text)
    if not found:
        return RangeResult(RangeStatus.NO_DATES)
    if len(found) > 2:
        return RangeResult(RangeStatus.BAD_FORMAT)

    rest = text
    for d in reversed(found):
        rest = rest[: d.start] + " " + rest[d.end :]
    if not _RANGE_FILLER_RE.fullmatch(rest):
        return RangeResult(RangeStatus.BAD_FORMAT)
    if any(not 1 <= d.month <= 12 for d in found):
        return RangeResult(RangeStatus.BAD_FORMAT)

    first, last = found[0], found[-1]
    clamped = _clamp_to_today(first, last, today) if len(found) == 2 else None
    if clamped is not None:
        start, end = clamped
    else:
        end = resolve_date(last.day, last.month, last.year, today)
        if end is None:
            return RangeResult(RangeStatus.INVALID)
        start = end
        if len(found) == 2:
            start = resolve_date(first.day, first.month, first.year, end)
            if start is None:
                return RangeResult(RangeStatus.INVALID)

    if end > today:
        return RangeResult(RangeStatus.FUTURE)
    if start > end:
        return RangeResult(RangeStatus.REVERSED)
    period = Period(PeriodKind.CUSTOM, start, end)
    if period.days > MAX_RANGE_DAYS:
        return RangeResult(RangeStatus.TOO_LONG)
    return RangeResult(RangeStatus.OK, period)


RANGE_ERRORS = {
    RangeStatus.NO_DATES: "Oraliqni tushunmadim. Masalan: <code>1.09 - 15.10</code>",
    RangeStatus.BAD_FORMAT: "Oraliqni tushunmadim. Masalan: <code>1.09 - 15.10</code>",
    RangeStatus.INVALID: "Bunday sana yo'q. Masalan: <code>1.09 - 15.10</code>",
    RangeStatus.FUTURE: "Oraliq kelajakka tushyapti — bugungacha bo'lgan sanani yozing.",
    RangeStatus.REVERSED: "Boshlanish sanasi tugash sanasidan keyin. Tartibni almashtiring.",
    RangeStatus.TOO_LONG: f"Oraliq ko'pi bilan {MAX_RANGE_DAYS} kun bo'lishi mumkin.",
}

# ---------------------------------------------------------------------------
# Grafik guruhlari
# ---------------------------------------------------------------------------


class Granularity(StrEnum):
    DAY = "day"
    WEEK = "week"  # dushanbadan
    MONTH = "month"


def bucket_for(period: Period) -> Granularity:
    if period.days <= 31:
        return Granularity.DAY
    if period.days <= 92:
        return Granularity.WEEK
    return Granularity.MONTH


def bucket_start(value: date, granularity: Granularity) -> date:
    if granularity is Granularity.WEEK:
        return value - timedelta(days=value.weekday())
    if granularity is Granularity.MONTH:
        return value.replace(day=1)
    return value


def fill_buckets(
    period: Period, granularity: Granularity, rows: list[tuple[date, int]]
) -> list[tuple[date, int]]:
    """Bo'sh guruhlarni 0 bilan to'ldiradi (grafikda kunlar tushib qolmasligi uchun)."""
    totals = dict(rows)
    result = []
    current = bucket_start(period.start, granularity)
    while current <= period.end:
        result.append((current, totals.get(current, 0)))
        if granularity is Granularity.DAY:
            current += timedelta(days=1)
        elif granularity is Granularity.WEEK:
            current += timedelta(days=7)
        else:
            current = add_months(current, 1)
    return result


# ---------------------------------------------------------------------------
# Foizlar
# ---------------------------------------------------------------------------


def shares(amounts: list[int]) -> list[int]:
    """Butun foizlar, yig'indisi aniq 100 (eng katta qoldiq usuli). Teng qoldiqda — oldingisi."""
    total = sum(amounts)
    if total == 0:
        return [0] * len(amounts)
    floors = [a * 100 // total for a in amounts]
    order = sorted(range(len(amounts)), key=lambda i: -(amounts[i] * 100 % total))
    for i in order[: 100 - sum(floors)]:
        floors[i] += 1
    return floors


_SHORT_UNITS = ((10**9, "mlrd"), (10**6, "mln"), (10**3, "ming"))


def format_short(amount: int) -> str:
    """Grafik yorliqlari uchun: 999, 45 ming, 1,3 mln, 2 mlrd."""
    if abs(amount) < 1000:
        return str(amount)
    for size, unit in _SHORT_UNITS:
        value = (Decimal(amount) / size).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        if abs(value) >= 1 or unit == "ming":
            text = f"{value:f}".rstrip("0").rstrip(".").replace(".", ",")
            return f"{text} {unit}"
    raise AssertionError  # "ming" doim qaytaradi


def change_percent(current: int, before: int) -> int | None:
    """O'zgarish foizi; oldingi davr 0 bo'lsa None ("—")."""
    if before == 0:
        return None
    value = Decimal(current - before) * 100 / Decimal(before)
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------------------
# Matn
# ---------------------------------------------------------------------------

MONTH_NAMES = [
    "yanvar",
    "fevral",
    "mart",
    "aprel",
    "may",
    "iyun",
    "iyul",
    "avgust",
    "sentabr",
    "oktabr",
    "noyabr",
    "dekabr",
]


def format_period(period: Period) -> str:
    """ "16 oktabr 2026", "1–16 oktabr 2026", "28 sentabr – 4 oktabr 2026", yillar har xil bo'lsa
    ikkalasida ham yil."""
    s, e = period.start, period.end
    end_text = f"{e.day} {MONTH_NAMES[e.month - 1]} {e.year}"
    if s == e:
        return end_text
    if (s.year, s.month) == (e.year, e.month):
        return f"{s.day}–{end_text}"
    start_text = f"{s.day} {MONTH_NAMES[s.month - 1]}"
    if s.year != e.year:
        start_text += f" {s.year}"
    return f"{start_text} – {end_text}"


@dataclass(frozen=True)
class CategoryTotal:
    name: str
    emoji: str | None
    amount: int
    count: int


@dataclass(frozen=True)
class ReportData:
    period: Period
    income: int
    expense: int
    categories: list[CategoryTotal]  # summasi bo'yicha kamayish tartibida
    prev_expense: int
    balance: int | None  # umumiy qoldiq; kirim umuman bo'lmasa None

    @property
    def is_empty(self) -> bool:
        return self.income == 0 and self.expense == 0


CHART_MAX_BARS = 8
REST_LABEL = "Qolganlari"  # "Boshqa" kategoriyasi bilan adashmasin


def fold_categories(
    categories: list[CategoryTotal], limit: int = CHART_MAX_BARS
) -> list[tuple[str, int]]:
    """Grafik uchun (nom, summa): ko'pi bilan `limit` ta, ortig'i bitta "Qolganlari (N ta)"ga."""
    if len(categories) <= limit:
        return [(c.name, c.amount) for c in categories]
    head, rest = categories[: limit - 1], categories[limit - 1 :]
    folded = [(c.name, c.amount) for c in head]
    folded.append((f"{REST_LABEL} ({len(rest)} ta)", sum(c.amount for c in rest)))
    return folded


def format_change(value: int | None) -> str:
    if value is None:
        return "—"
    return f"+{value}%" if value > 0 else ("0%" if value == 0 else f"−{abs(value)}%")


def build_report_text(data: ReportData) -> str:
    lines = [f"📊 <b>{format_period(data.period)}</b>", ""]
    if data.is_empty:
        lines.append("Bu davrda yozuv yo'q.")
    else:
        lines += [
            f"💵 Kirim:  {format_amount(data.income)}",
            f"💸 Chiqim:  {format_amount(data.expense)}",
            f"⚖️ Farq:  <b>{format_amount(data.income - data.expense)}</b>",
        ]
        if data.categories:
            lines += ["", "<b>Chiqim kategoriyalar bo'yicha:</b>"]
            percents = shares([c.amount for c in data.categories])
            for c, pct in zip(data.categories, percents, strict=True):
                label = escape(category_label(c.name, c.emoji), quote=False)
                lines.append(f"{label} — {format_amount(c.amount)} ({pct}%)")

    if data.expense or data.prev_expense:
        prev = previous(data.period)
        change = format_change(change_percent(data.expense, data.prev_expense))
        lines += [
            "",
            f"O'tgan davr ({format_period(prev)}): chiqim {format_amount(data.prev_expense)}, "
            f"o'zgarish {change}",
        ]
    if data.balance is not None:
        lines.append(f"\n💰 Umumiy qoldiq: <b>{format_amount(data.balance)}</b>")
    return "\n".join(lines)


def fits_caption(html: str) -> bool:
    """Matn rasm izohiga sig'adimi; sig'masa rasm va matn alohida yuboriladi."""
    plain = re.sub(r"<[^>]+>", "", html)
    for entity, char in (("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&")):
        plain = plain.replace(entity, char)
    return len(plain.encode("utf-16-le")) // 2 <= CAPTION_LIMIT
