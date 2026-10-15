"""Yozuv kartasining matni va sana tanlovi."""

from __future__ import annotations

from datetime import date, timedelta
from html import escape

from bot.db.models import TransactionType
from bot.services.parser import DATE_WINDOW_DAYS

RELATIVE_DAYS = {0: "bugun", 1: "kecha", 2: "o'tgan kuni"}


def format_amount(amount: int) -> str:
    sign = "−" if amount < 0 else ""
    return f"{sign}{abs(amount):,}".replace(",", " ") + " so'm"


def format_date(value: date, today: date) -> str:
    label = RELATIVE_DAYS.get((today - value).days)
    text = value.strftime("%d.%m.%Y")
    return f"{text} ({label})" if label else text


def date_choices(today: date) -> list[date]:
    """Ruxsat etilgan sanalar: bugundan 30 kun orqagacha (30-kun ham kiradi), yangisi birinchi."""
    return [today - timedelta(days=i) for i in range(DATE_WINDOW_DAYS + 1)]


def is_allowed_date(value: date, today: date) -> bool:
    return today - timedelta(days=DATE_WINDOW_DAYS) <= value <= today


def category_label(name: str, emoji: str | None) -> str:
    return f"{emoji} {name}" if emoji else name


def render_ai_confirm(*, amount: int, category: str | None, kind: TransactionType) -> str:
    """AI topgan summani tasdiqlash xabari. category — tayyor yorliq yoki None."""
    lines = [
        "🤖 <b>Shunday tushundim:</b>",
        f"{'💵' if kind is TransactionType.INCOME else '💸'} {format_amount(amount)}",
    ]
    if kind is TransactionType.EXPENSE:
        lines.append(
            f"📂 {escape(category, quote=False) if category else 'kategoriyani keyin tanlaysiz'}"
        )
    lines += ["", "To'g'rimi?"]
    return "\n".join(lines)


def render_category_changed(
    *, amount: int, old: str | None, new: str, learned: str | None = None
) -> str:
    """Kategoriya o'zgargani haqida alohida xabar. old/new — tayyor yorliqlar."""
    before = escape(old, quote=False) if old else "—"
    lines = [
        "📂 <b>Kategoriya o'zgartirildi</b>",
        f"💸 {format_amount(amount)}: {before} → <b>{escape(new, quote=False)}</b>",
    ]
    if learned:
        lines.append(
            f"<i>«{escape(learned, quote=False)}» so'zi eslab qolindi — "
            "keyingi safar shu kategoriya avtomatik tanlanadi</i>"
        )
    return "\n".join(lines)


def render_card(
    *,
    kind: TransactionType,
    amount: int,
    occurred_on: date,
    today: date,
    category: str | None = None,  # tayyor yorliq: "🚕 Transport"
    balance: int | None = None,  # None — kirim yo'q, qoldiq qatori chiqmaydi
    rounded: bool = False,
    ai_category: bool = False,  # kategoriyani AI tanlagan
) -> str:
    if kind is TransactionType.INCOME:
        lines = ["✅ <b>Kirim saqlandi</b>", f"💵 {format_amount(amount)}"]
    else:
        lines = ["✅ <b>Xarajat saqlandi</b>", f"💸 {format_amount(amount)}"]
        lines.append(f"📂 {escape(category or '—', quote=False)}")
        if ai_category:
            lines.append("<i>🤖 Kategoriyani AI tanladi — xato bo'lsa, «Kategoriya»ni bosing</i>")
    lines.append(f"📅 {format_date(occurred_on, today)}")
    if rounded:
        lines.append("<i>Tiyin eng yaqin so'mga yaxlitlandi</i>")
    if balance is not None:
        lines.append(f"\n💰 Umumiy qoldiq: <b>{format_amount(balance)}</b>")
    return "\n".join(lines)
