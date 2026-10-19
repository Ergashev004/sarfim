from datetime import date

from bot.db.models import Category, Transaction, TransactionType
from bot.services.history import EMPTY, render_history, short_note

TODAY = date(2026, 10, 16)


def _tx(kind, amount, day, note=None) -> Transaction:
    return Transaction(type=kind, amount=amount, occurred_on=day, note=note)


def test_empty():
    assert render_history([], TODAY) == EMPTY


def test_expense_and_income_lines():
    rows = [
        (
            _tx(TransactionType.EXPENSE, 30_000, TODAY, "taksi 30000"),
            Category(name="Transport", emoji="🚕"),
        ),
        (_tx(TransactionType.INCOME, 5_000_000, date(2026, 10, 1), "+5 mln oylik"), None),
    ]
    text = render_history(rows, TODAY)
    assert "<b>1.</b> 💸 30 000 so'm · 🚕 Transport" in text
    assert "16.10.2026 (bugun) · <i>taksi 30000</i>" in text
    assert "<b>2.</b> 💵 +5 000 000 so'm · kirim" in text
    assert "01.10.2026 · <i>+5 mln oylik</i>" in text


def test_note_and_category_escaped():
    rows = [
        (_tx(TransactionType.EXPENSE, 1000, TODAY, "<b>x</b>"), Category(name="A&B", emoji=None))
    ]
    text = render_history(rows, TODAY)
    assert "&lt;b&gt;x&lt;/b&gt;" in text and "A&amp;B" in text


def test_short_note():
    assert short_note(None) is None
    assert short_note("a" * 40) == "a" * 40
    long = short_note("a" * 41)
    assert len(long) == 40 and long.endswith("…")
