"""Kiritish pipeline'i: matn -> sana -> summa -> kirim/chiqim -> kategoriya.

Telegram ham, baza ham yo'q: matn va `today` kiradi, `Entry` chiqadi.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date
from enum import StrEnum

from bot.db.models import TransactionType
from bot.services.categorizer import categorize, is_income
from bot.services.parser import AmountStatus, DateStatus, parse_amount, parse_date

_DATE_ERRORS = {
    DateStatus.INVALID: "Bunday sana yo'q. Masalan: <code>taksi 30000 5.10</code>",
    DateStatus.FUTURE: "Kelajakdagi sanaga yozib bo'lmaydi.",
    DateStatus.TOO_OLD: "Faqat oxirgi 30 kun ichidagi sanaga yozish mumkin.",
}


class EntryStatus(StrEnum):
    READY = "ready"  # saqlashga tayyor
    NEED_CATEGORY = "need_category"  # kategoriya tugmalari kerak
    NEED_AMOUNT = "need_amount"  # summani so'raymiz
    BAD_AMOUNT = "bad_amount"
    BAD_DATE = "bad_date"


class AmountQuestion(StrEnum):
    """Nega summa so'ralyapti — foydalanuvchiga aniq tushuntirish uchun."""

    MISSING = "missing"
    MULTIPLE = "multiple"
    TWO_DATES = "two_dates"


@dataclass(frozen=True)
class Entry:
    status: EntryStatus
    kind: TransactionType = TransactionType.EXPENSE
    amount: int | None = None
    rounded: bool = False
    occurred_on: date | None = None
    category: str | None = None  # standart kategoriya nomi (kalit so'zdan)
    note: str = ""
    reason: str | None = None  # BAD_* holatda foydalanuvchiga ko'rsatiladigan matn
    question: AmountQuestion | None = None

    def to_dict(self) -> dict:
        """FSM xotirasida saqlash uchun (faqat JSON turlari)."""
        data = asdict(self)
        data["occurred_on"] = self.occurred_on.isoformat() if self.occurred_on else None
        return data

    @classmethod
    def from_dict(cls, data: dict) -> Entry:
        data = dict(data)
        data["status"] = EntryStatus(data["status"])
        data["kind"] = TransactionType(data["kind"])
        if data["occurred_on"]:
            data["occurred_on"] = date.fromisoformat(data["occurred_on"])
        if data["question"]:
            data["question"] = AmountQuestion(data["question"])
        return cls(**data)


def _next_status(entry: Entry) -> EntryStatus:
    if entry.kind is TransactionType.EXPENSE and entry.category is None:
        return EntryStatus.NEED_CATEGORY
    return EntryStatus.READY


def parse_entry(text: str, today: date) -> Entry:
    note = text.strip()

    # 1. Sana (avval sana, keyin qolgan matndan summa)
    date_res = parse_date(text, today)
    if date_res.status in _DATE_ERRORS:
        return Entry(EntryStatus.BAD_DATE, note=note, reason=_DATE_ERRORS[date_res.status])
    rest = date_res.rest

    # 2. Kirim/chiqim va kategoriya — summa so'ralsa ham keyin kerak bo'ladi
    kind = TransactionType.INCOME if is_income(text) else TransactionType.EXPENSE
    category = categorize(rest) if kind is TransactionType.EXPENSE else None
    base = Entry(
        EntryStatus.NEED_AMOUNT,
        kind=kind,
        occurred_on=date_res.value,
        category=category,
        note=note,
    )

    # Matnda ikkinchi sana ham bo'lsa ("5.10 kecha") — qaysi raqam summa ekani noaniq
    if parse_date(rest, today).status is not DateStatus.NOT_FOUND:
        return replace(base, question=AmountQuestion.TWO_DATES)

    # 3. Summa
    amount_res = parse_amount(rest)
    match amount_res.status:
        case AmountStatus.MISSING:
            return replace(base, question=AmountQuestion.MISSING)
        case AmountStatus.MULTIPLE:
            return replace(base, question=AmountQuestion.MULTIPLE)
        case AmountStatus.INVALID:
            return replace(base, status=EntryStatus.BAD_AMOUNT, reason=amount_res.reason)

    entry = replace(base, amount=amount_res.value, rounded=amount_res.rounded)
    # 4. Kategoriya
    return replace(entry, status=_next_status(entry))


def with_amount(entry: Entry, text: str) -> Entry | None:
    """Summa kutilayotgan yozuvga foydalanuvchi alohida yuborgan summani qo'shadi.

    Matnda bitta summa topilmasa None — demak bu summa emas, yangi yozuv.
    """
    amount_res = parse_amount(text)
    match amount_res.status:
        case AmountStatus.OK:
            done = replace(
                entry, amount=amount_res.value, rounded=amount_res.rounded, question=None
            )
            return replace(done, status=_next_status(done), reason=None)
        case AmountStatus.INVALID:
            return replace(entry, status=EntryStatus.BAD_AMOUNT, reason=amount_res.reason)
        case _:
            return None


def with_category(entry: Entry, category: str) -> Entry:
    return replace(entry, category=category, status=EntryStatus.READY)
