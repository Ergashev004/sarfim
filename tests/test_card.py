from datetime import date

from bot.db.models import TransactionType
from bot.keyboards.entry import (
    TxAction,
    confirm_keyboard,
    date_keyboard,
    delete_confirm_keyboard,
    edit_keyboard,
    record_keyboard,
)
from bot.services.card import (
    date_choices,
    format_amount,
    is_allowed_date,
    render_card,
    render_category_changed,
)

TODAY = date(2026, 10, 11)


def test_format_amount():
    assert format_amount(30_000) == "30 000 so'm"
    assert format_amount(1_000_000_000) == "1 000 000 000 so'm"
    assert format_amount(-50_000) == "−50 000 so'm"


def test_expense_card_without_income_has_no_balance():
    text = render_card(
        kind=TransactionType.EXPENSE,
        amount=30_000,
        occurred_on=TODAY,
        today=TODAY,
        category="🚕 Transport",
    )
    assert "30 000 so'm" in text
    assert "🚕 Transport" in text
    assert "11.10.2026 (bugun)" in text
    assert "qoldiq" not in text


def test_card_with_negative_balance():
    text = render_card(
        kind=TransactionType.EXPENSE,
        amount=30_000,
        occurred_on=date(2026, 10, 10),
        today=TODAY,
        category="Kiyim",
        balance=-20_000,
    )
    assert "(kecha)" in text
    assert "Umumiy qoldiq: <b>−20 000 so'm</b>" in text


def test_income_card_has_no_category():
    text = render_card(
        kind=TransactionType.INCOME,
        amount=5_000_000,
        occurred_on=TODAY,
        today=TODAY,
        balance=5_000_000,
    )
    assert "Kirim" in text
    assert "📂" not in text


def test_rounded_note_and_html_escape():
    text = render_card(
        kind=TransactionType.EXPENSE,
        amount=12_501,
        occurred_on=TODAY,
        today=TODAY,
        category="<b>x</b>",
        rounded=True,
    )
    assert "yaxlitlandi" in text
    assert "&lt;b&gt;x&lt;/b&gt;" in text


def test_date_choices_window():
    days = date_choices(TODAY)
    assert len(days) == 31  # bugun + 30 kun orqaga
    assert days[0] == TODAY
    assert days[-1] == date(2026, 9, 11)
    assert is_allowed_date(date(2026, 9, 11), TODAY)
    assert not is_allowed_date(date(2026, 9, 10), TODAY)
    assert not is_allowed_date(date(2026, 10, 12), TODAY)


def _buttons(markup):
    return [b for row in markup.inline_keyboard for b in row]


def _actions(markup) -> list[tuple[str, str]]:
    return [(b.text, TxAction.unpack(b.callback_data).action) for b in _buttons(markup)]


def test_card_keyboards():
    assert _actions(confirm_keyboard(1)) == [("✅ To'g'ri", "ok"), ("✏️ O'zgartirish", "cat")]
    assert _actions(record_keyboard(1)) == [("✏️ Tahrirlash", "edit"), ("🗑 O'chirish", "del")]
    assert _actions(delete_confirm_keyboard(1)) == [
        ("Ha, o'chirish", "delok"),
        ("Bekor qilish", "back"),
    ]


def test_edit_keyboard():
    expense = _actions(edit_keyboard(1, with_category=True))
    income = _actions(edit_keyboard(1, with_category=False))
    assert expense == [
        ("💵 Summa", "amount"),
        ("📂 Kategoriya", "cat"),
        ("📅 Sana", "date"),
        ("⬅️ Orqaga", "back"),
    ]
    assert ("📂 Kategoriya", "cat") not in income


def test_date_keyboard_layout():
    markup = date_keyboard(123_456_789, date_choices(TODAY))
    rows = markup.inline_keyboard
    assert [b.text for b in rows[0]] == ["Bugun", "Kecha", "O'tgan kuni"]
    dates = [TxAction.unpack(b.callback_data) for b in _buttons(markup)[:-1]]
    assert len(dates) == 31
    assert date.fromordinal(dates[-1].value) == date(2026, 9, 11)
    assert rows[-1][0].text == "⬅️ Orqaga"
    # Telegram callback_data cheklovi — 64 bayt
    assert all(len(b.callback_data.encode()) <= 64 for b in _buttons(markup))


def test_category_changed_message():
    text = render_category_changed(
        amount=210000, old="🚕 Transport", new="🏷 Moshina", learned="balon"
    )
    assert "Kategoriya o'zgartirildi" in text
    assert "210 000 so'm: 🚕 Transport → <b>🏷 Moshina</b>" in text
    assert "«balon» so'zi eslab qolindi" in text


def test_category_changed_without_learned_word_and_html_escaped():
    text = render_category_changed(amount=5000, old=None, new="<Uy>")
    assert "— → <b>&lt;Uy&gt;</b>" in text
    assert "eslab qolindi" not in text
