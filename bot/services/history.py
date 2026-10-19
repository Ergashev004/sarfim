"""/oxirgi: oxirgi yozuvlar ro'yxati matni."""

from __future__ import annotations

from datetime import date
from html import escape

from bot.db.models import Category, Transaction, TransactionType
from bot.services.card import category_label, format_amount, format_date

HISTORY_LIMIT = 10
NOTE_MAX_LEN = 40
EMPTY = "Hali yozuv yo'q. Xarajat yozing, masalan: <code>taksi 30000</code>"


def short_note(note: str | None) -> str | None:
    if not note:
        return None
    return note if len(note) <= NOTE_MAX_LEN else note[: NOTE_MAX_LEN - 1].rstrip() + "…"


def render_history(rows: list[tuple[Transaction, Category | None]], today: date) -> str:
    if not rows:
        return EMPTY
    lines = ["🕘 <b>Oxirgi yozuvlar</b>", ""]
    for i, (tx, category) in enumerate(rows, 1):
        if tx.type is TransactionType.INCOME:
            head = f"💵 +{format_amount(tx.amount)} · kirim"
        else:
            label = category_label(category.name, category.emoji) if category else "—"
            head = f"💸 {format_amount(tx.amount)} · {escape(label, quote=False)}"
        lines.append(f"<b>{i}.</b> {head}")
        details = format_date(tx.occurred_on, today)
        if note := short_note(tx.note):
            details += f" · <i>{escape(note, quote=False)}</i>"
        lines.append(f"     {details}")
    lines += ["", "Tahrirlash yoki o'chirish uchun raqamni bosing."]
    return "\n".join(lines)
