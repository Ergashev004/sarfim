from datetime import date

import pytest

from bot.services.report import (
    CategoryTotal,
    Granularity,
    Period,
    PeriodKind,
    RangeStatus,
    ReportData,
    add_months,
    bucket_for,
    build_report_text,
    change_percent,
    fill_buckets,
    fits_caption,
    fold_categories,
    format_period,
    format_short,
    parse_range,
    period_for,
    previous,
    shares,
)

TODAY = date(2026, 10, 16)  # payshanba

# ---------------------------------------------------------------------------
# Davrlar
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "today", "start"),
    [
        (PeriodKind.TODAY, TODAY, TODAY),
        (PeriodKind.WEEK, TODAY, date(2026, 10, 12)),
        (PeriodKind.WEEK, date(2026, 10, 12), date(2026, 10, 12)),  # dushanba
        (PeriodKind.WEEK, date(2026, 10, 18), date(2026, 10, 12)),  # yakshanba
        (PeriodKind.WEEK, date(2027, 1, 2), date(2026, 12, 28)),  # yil almashishi
        (PeriodKind.MONTH, TODAY, date(2026, 10, 1)),
        (PeriodKind.MONTH, date(2026, 10, 1), date(2026, 10, 1)),
        (PeriodKind.MONTHS_3, TODAY, date(2026, 8, 1)),
        (PeriodKind.MONTHS_3, date(2026, 5, 31), date(2026, 3, 1)),
        (PeriodKind.MONTHS_3, date(2026, 2, 10), date(2025, 12, 1)),
        (PeriodKind.MONTHS_6, TODAY, date(2026, 5, 1)),
        (PeriodKind.YEAR, TODAY, date(2025, 11, 1)),
    ],
)
def test_period_for(kind, today, start):
    period = period_for(kind, today)
    assert (period.start, period.end) == (start, today)


def test_period_for_custom_is_not_preset():
    with pytest.raises(ValueError):
        period_for(PeriodKind.CUSTOM, TODAY)


@pytest.mark.parametrize(
    ("value", "months", "expected"),
    [
        (date(2026, 10, 31), -1, date(2026, 9, 30)),
        (date(2026, 3, 31), -1, date(2026, 2, 28)),
        (date(2028, 3, 31), -1, date(2028, 2, 29)),  # kabisa yil
        (date(2026, 1, 15), -1, date(2025, 12, 15)),
        (date(2026, 12, 1), 1, date(2027, 1, 1)),
        (date(2026, 10, 1), -11, date(2025, 11, 1)),
    ],
)
def test_add_months(value, months, expected):
    assert add_months(value, months) == expected


@pytest.mark.parametrize(
    ("kind", "today", "prev_start", "prev_end"),
    [
        (PeriodKind.TODAY, TODAY, date(2026, 10, 15), date(2026, 10, 15)),
        (PeriodKind.WEEK, TODAY, date(2026, 10, 5), date(2026, 10, 9)),
        (PeriodKind.MONTH, TODAY, date(2026, 9, 1), date(2026, 9, 16)),
        # 31-oktabr: sentabrda 31-kun yo'q -> oy oxiriga qisqartiriladi
        (PeriodKind.MONTH, date(2026, 10, 31), date(2026, 9, 1), date(2026, 9, 30)),
        (PeriodKind.MONTH, date(2026, 3, 31), date(2026, 2, 1), date(2026, 2, 28)),
        (PeriodKind.MONTH, date(2026, 1, 10), date(2025, 12, 1), date(2025, 12, 10)),
        (PeriodKind.MONTHS_3, TODAY, date(2026, 5, 1), date(2026, 7, 16)),
        (PeriodKind.MONTHS_3, date(2026, 5, 31), date(2025, 12, 1), date(2026, 2, 28)),
        (PeriodKind.YEAR, TODAY, date(2024, 11, 1), date(2025, 10, 16)),
    ],
)
def test_previous(kind, today, prev_start, prev_end):
    prev = previous(period_for(kind, today))
    assert (prev.start, prev.end) == (prev_start, prev_end)


def test_previous_custom_same_length_right_before():
    period = Period(PeriodKind.CUSTOM, date(2026, 9, 1), date(2026, 9, 10))
    prev = previous(period)
    assert (prev.start, prev.end) == (date(2026, 8, 22), date(2026, 8, 31))
    assert prev.days == period.days


# ---------------------------------------------------------------------------
# Ixtiyoriy oraliq
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "start", "end"),
    [
        ("1.09 - 15.10", date(2026, 9, 1), date(2026, 10, 15)),
        ("1.09-15.10", date(2026, 9, 1), date(2026, 10, 15)),
        ("1.09 – 15.10", date(2026, 9, 1), date(2026, 10, 15)),  # en dash
        ("01.09.2026 — 15.10.2026", date(2026, 9, 1), date(2026, 10, 15)),
        ("1/09 15/10", date(2026, 9, 1), date(2026, 10, 15)),
        ("1 sentabr - 15 oktabr", date(2026, 9, 1), date(2026, 10, 15)),
        ("1-sentabrdan 15-oktabrgacha", date(2026, 9, 1), date(2026, 10, 15)),
        ("1.09 dan 15.10 gacha", date(2026, 9, 1), date(2026, 10, 15)),
        ("16.10", TODAY, TODAY),  # bitta sana = bitta kun
        # ikkalasi kelajakda — o'tgan yil
        ("1.11 - 30.11", date(2025, 11, 1), date(2025, 11, 30)),
        ("17.10 - 20.10", date(2025, 10, 17), date(2025, 10, 20)),
        # boshlanish oxirgi sanaga nisbatan aniqlanadi: dekabr o'tgan yilniki
        ("20.12 - 10.01", date(2025, 12, 20), date(2026, 1, 10)),
        # boshlanish o'tgan, tugash kelajakda — tugash bugungacha qisqaradi
        ("10.10 - 20.10", date(2026, 10, 10), TODAY),
        ("16.10 - 17.10", TODAY, TODAY),
        ("1.01 - 31.12", date(2026, 1, 1), TODAY),
        ("1.10.2026 - 20.10.2026", date(2026, 10, 1), TODAY),
        ("1.10.2026 - 20.10", date(2026, 10, 1), TODAY),
        ("1.12 - 15.01.2026", date(2025, 12, 1), date(2026, 1, 15)),
        ("17.10.2025 - 16.10.2026", date(2025, 10, 17), date(2026, 10, 16)),  # 365 kun
    ],
)
def test_parse_range_ok(text, start, end):
    result = parse_range(text, TODAY)
    assert result.status is RangeStatus.OK
    assert (result.period.start, result.period.end) == (start, end)
    assert result.period.kind is PeriodKind.CUSTOM


@pytest.mark.parametrize(
    ("text", "status"),
    [
        ("", RangeStatus.NO_DATES),
        ("sentabr", RangeStatus.NO_DATES),
        ("o'tgan oy", RangeStatus.NO_DATES),
        ("taksi 30000", RangeStatus.NO_DATES),
        ("1.09 - 15.10 - 20.10", RangeStatus.BAD_FORMAT),
        ("1.09 taksi 15.10", RangeStatus.BAD_FORMAT),
        ("1.13 - 15.10", RangeStatus.BAD_FORMAT),  # 13-oy yo'q
        ("31.02 - 15.10", RangeStatus.INVALID),
        ("1.09 - 31.09", RangeStatus.INVALID),
        ("17.10.2026 - 20.10.2026", RangeStatus.FUTURE),
        ("20.10.2026", RangeStatus.FUTURE),
        ("1.01.2025 - 20.10.2026", RangeStatus.TOO_LONG),  # qisqartirilgandan keyin ham
        ("15.10.2026 - 1.09.2026", RangeStatus.REVERSED),
        ("1.01.2025 - 15.10.2026", RangeStatus.TOO_LONG),
        ("15.10.2025 - 16.10.2026", RangeStatus.TOO_LONG),  # 367 kun
    ],
)
def test_parse_range_errors(text, status):
    result = parse_range(text, TODAY)
    assert result.status is status
    assert result.period is None


def test_parse_range_max_366_days_in_leap_year():
    result = parse_range("1.03.2027 - 29.02.2028", date(2028, 3, 1))
    assert result.status is RangeStatus.OK
    assert result.period.days == 366


# ---------------------------------------------------------------------------
# Grafik guruhlari
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("days", "expected"),
    [(1, Granularity.DAY), (31, Granularity.DAY), (32, Granularity.WEEK), (92, Granularity.WEEK)],
)
def test_bucket_for(days, expected):
    start = date(2026, 1, 1)
    period = Period(PeriodKind.CUSTOM, start, date.fromordinal(start.toordinal() + days - 1))
    assert bucket_for(period) is expected


def test_bucket_for_long_periods_monthly():
    assert bucket_for(period_for(PeriodKind.MONTHS_6, TODAY)) is Granularity.MONTH
    assert bucket_for(period_for(PeriodKind.YEAR, TODAY)) is Granularity.MONTH


def test_fill_buckets_days():
    period = Period(PeriodKind.CUSTOM, date(2026, 10, 1), date(2026, 10, 4))
    rows = [(date(2026, 10, 2), 500)]
    assert fill_buckets(period, Granularity.DAY, rows) == [
        (date(2026, 10, 1), 0),
        (date(2026, 10, 2), 500),
        (date(2026, 10, 3), 0),
        (date(2026, 10, 4), 0),
    ]


def test_fill_buckets_weeks_start_on_monday_before_period():
    period = Period(PeriodKind.CUSTOM, date(2026, 10, 1), date(2026, 10, 16))  # payshanbadan
    keys = [d for d, _ in fill_buckets(period, Granularity.WEEK, [])]
    assert keys == [date(2026, 9, 28), date(2026, 10, 5), date(2026, 10, 12)]


def test_fill_buckets_months():
    keys = [d for d, _ in fill_buckets(period_for(PeriodKind.MONTHS_3, TODAY), "month", [])]
    assert keys == [date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1)]


# ---------------------------------------------------------------------------
# Foizlar
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("amounts", "expected"),
    [
        ([100, 100, 100], [34, 33, 33]),  # 33.3 x 3 — yig'indi 100
        ([1, 1, 1, 1, 1, 1], [17, 17, 17, 17, 16, 16]),
        ([6_710_000, 770_060, 600_000], [83, 10, 7]),
        ([999, 1], [100, 0]),
        ([5000], [100]),
        ([], []),
    ],
)
def test_shares_sum_to_100(amounts, expected):
    result = shares(amounts)
    assert result == expected
    if amounts:
        assert sum(result) == 100


def test_shares_zero_total():
    assert shares([0, 0]) == [0, 0]


@pytest.mark.parametrize(
    ("current", "before", "expected"),
    [
        (200, 100, 100),
        (50, 100, -50),
        (100, 100, 0),
        (0, 100, -100),
        (1005, 1000, 1),  # 0.5 -> yuqoriga
        (100, 0, None),  # oldingi davr 0 -> "—"
        (0, 0, None),
    ],
)
def test_change_percent(current, before, expected):
    assert change_percent(current, before) == expected


# ---------------------------------------------------------------------------
# Matn
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (TODAY, TODAY, "16 oktabr 2026"),
        (date(2026, 10, 1), TODAY, "1–16 oktabr 2026"),
        (date(2026, 9, 28), date(2026, 10, 4), "28 sentabr – 4 oktabr 2026"),
        (date(2025, 12, 28), date(2026, 1, 3), "28 dekabr 2025 – 3 yanvar 2026"),
    ],
)
def test_format_period(start, end, expected):
    assert format_period(Period(PeriodKind.CUSTOM, start, end)) == expected


def _data(**kw) -> ReportData:
    base = dict(
        period=period_for(PeriodKind.MONTH, TODAY),
        income=0,
        expense=0,
        categories=[],
        prev_expense=0,
        balance=None,
    )
    return ReportData(**(base | kw))


def test_report_text_full():
    text = build_report_text(
        _data(
            income=5_000_000,
            expense=8_000_000,
            categories=[
                CategoryTotal("Moshina", "🚗", 6_000_000, 3),
                CategoryTotal("Kafe/restoran", "☕", 2_000_000, 1),
            ],
            prev_expense=4_000_000,
            balance=-1_000_000,
        )
    )
    assert "1–16 oktabr 2026" in text
    assert "Kirim:  5 000 000 so'm" in text
    assert "Chiqim:  8 000 000 so'm" in text
    assert "Farq:  <b>−3 000 000 so'm</b>" in text
    assert "🚗 Moshina — 6 000 000 so'm (75%)" in text
    assert "☕ Kafe/restoran — 2 000 000 so'm (25%)" in text
    assert "📈 Chiqim o'tgan davrga nisbatan: <b>+100%</b>" in text
    assert "<i>1–16 sentabr 2026: 4 000 000 so'm</i>" in text
    assert "Umumiy qoldiq: <b>−1 000 000 so'm</b>" in text


def test_report_text_empty():
    text = build_report_text(_data())
    assert "Bu davrda yozuv yo'q." in text
    assert "Kirim" not in text
    assert "o'tgan davr" not in text


def test_report_text_empty_but_previous_had_expense():
    text = build_report_text(_data(prev_expense=100_000))
    assert "Bu davrda yozuv yo'q." in text
    assert "📉 Chiqim o'tgan davrga nisbatan: <b>−100%</b>" in text


def test_report_text_income_only():
    text = build_report_text(_data(income=5_000_000, balance=5_000_000))
    assert "yozuv yo'q" not in text
    assert "Kirim:  5 000 000 so'm" in text
    assert "Farq:  <b>5 000 000 so'm</b>" in text
    assert "kategoriyalar bo'yicha" not in text
    assert "o'tgan davr" not in text


def test_report_text_previous_zero_hides_comparison():
    text = build_report_text(
        _data(expense=10_000, categories=[CategoryTotal("Transport", "🚕", 10_000, 1)])
    )
    assert "o'tgan davr" not in text
    assert "Umumiy qoldiq" not in text  # kirim yo'q


def test_report_text_escapes_category_name():
    text = build_report_text(
        _data(expense=1000, categories=[CategoryTotal("<b>X</b>", None, 1000, 1)])
    )
    assert "&lt;b&gt;X&lt;/b&gt; — 1 000 so'm (100%)" in text


def test_typical_report_fits_photo_caption():
    # 11 standart + 3 shaxsiy kategoriya, million so'mlik summalar
    categories = [CategoryTotal("Aloqa/internet", "📱", 12_345_678, 5) for _ in range(14)]
    text = build_report_text(
        _data(
            period=Period(PeriodKind.CUSTOM, date(2025, 12, 28), date(2026, 1, 3)),
            income=99_999_999,
            expense=172_839_492,
            categories=categories,
            prev_expense=99_999_999,
            balance=-99_999_999,
        )
    )
    assert fits_caption(text)


def test_worst_case_report_does_not_fit_caption():
    categories = [CategoryTotal("Ж" * 32, "🎮", 999_999_999, 1) for _ in range(14)]
    text = build_report_text(
        _data(expense=13_999_999_986, categories=categories, prev_expense=1, balance=-1)
    )
    assert not fits_caption(text)


def test_fits_caption_counts_utf16_and_ignores_tags():
    assert fits_caption("<b>" + "a" * 1024 + "</b>")
    assert not fits_caption("a" * 1025)
    assert fits_caption("🎮" * 512)  # emoji = 2 birlik
    assert not fits_caption("🎮" * 513)
    assert fits_caption("&lt;" * 1024)  # ekranda bitta "<"


# ---------------------------------------------------------------------------
# Grafik yordamchilari
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (0, "0"),
        (999, "999"),
        (1_000, "1 ming"),
        (45_000, "45 ming"),
        (15_300, "15,3 ming"),
        (15_350, "15,4 ming"),  # yarmi yuqoriga
        (999_950, "1 mln"),  # "1000 ming" emas
        (1_250_000, "1,3 mln"),
        (120_000_000, "120 mln"),
        (1_000_000_000, "1 mlrd"),
    ],
)
def test_format_short(amount, expected):
    assert format_short(amount) == expected


def _cats(n: int) -> list[CategoryTotal]:
    return [CategoryTotal(f"K{i}", None, (n - i) * 1000, 1) for i in range(n)]


def test_fold_categories_keeps_up_to_limit():
    assert fold_categories(_cats(8)) == [(f"K{i}", (8 - i) * 1000) for i in range(8)]


def test_fold_categories_merges_tail():
    folded = fold_categories(_cats(10))
    assert len(folded) == 8
    assert folded[:7] == [(f"K{i}", (10 - i) * 1000) for i in range(7)]
    assert folded[7] == ("Qolganlari (3 ta)", 3000 + 2000 + 1000)
    assert sum(a for _, a in folded) == sum(c.amount for c in _cats(10))
