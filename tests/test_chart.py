from datetime import date

from bot.services.chart import bucket_label, render_chart
from bot.services.report import CategoryTotal, Granularity, Period, PeriodKind, fill_buckets

PNG = b"\x89PNG\r\n\x1a\n"
OCT = Period(PeriodKind.MONTH, date(2026, 10, 1), date(2026, 10, 16))


def _cats(n: int) -> list[CategoryTotal]:
    return [CategoryTotal(f"Kategoriya {i}", "🚕", (n - i) * 10_000, 1) for i in range(n)]


def test_renders_png_with_timeline():
    buckets = fill_buckets(OCT, Granularity.DAY, [(date(2026, 10, 3), 50_000)])
    png = render_chart(OCT, _cats(3), buckets, Granularity.DAY)
    assert png.startswith(PNG)


def test_single_day_without_timeline():
    day = Period(PeriodKind.TODAY, date(2026, 10, 16), date(2026, 10, 16))
    png = render_chart(day, _cats(1), [(day.start, 10_000)], Granularity.DAY)
    assert png.startswith(PNG)


def test_many_categories_and_long_year():
    year = Period(PeriodKind.YEAR, date(2025, 11, 1), date(2026, 10, 16))
    buckets = fill_buckets(year, Granularity.MONTH, [])
    with_cats = render_chart(year, _cats(14), buckets, Granularity.MONTH)
    assert with_cats.startswith(PNG)


def test_bucket_labels():
    d = date(2026, 10, 5)
    assert bucket_label(d, Granularity.DAY) == "5"
    assert bucket_label(d, Granularity.WEEK) == "05.10"
    assert bucket_label(d, Granularity.MONTH) == "okt"
