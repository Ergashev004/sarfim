"""Hisobot rasmi (PNG): chiqim kategoriyalar bo'yicha va vaqt bo'yicha.

pyplot ishlatilmaydi — faqat Figure (global holat yo'q, asyncio.to_thread da xavfsiz).
"""

from __future__ import annotations

from datetime import date
from io import BytesIO

from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, MaxNLocator

from bot.services.report import (
    MONTH_NAMES,
    CategoryTotal,
    Granularity,
    Period,
    fold_categories,
    format_period,
    format_short,
    shares,
)

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e4e3df"
BAR = "#2a78d6"

WIDTH_IN = 8
DPI = 150


def bucket_label(value: date, granularity: Granularity) -> str:
    if granularity is Granularity.MONTH:
        return MONTH_NAMES[value.month - 1][:3]
    if granularity is Granularity.WEEK:
        return value.strftime("%d.%m")
    return str(value.day)


def _style(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)


def _categories(ax, categories: list[CategoryTotal]) -> None:
    bars = fold_categories(categories)
    names = [name for name, _ in bars]
    amounts = [amount for _, amount in bars]
    rows = range(len(bars))
    ax.barh(rows, amounts, height=0.6, color=BAR)
    ax.set_yticks(list(rows), names, fontsize=10, color=TEXT)
    ax.invert_yaxis()  # kattasi tepada
    ax.set_xticks([])
    ax.spines["bottom"].set_visible(False)
    ax.set_xlim(0, max(amounts) * 1.3)  # o'ngda yorliq uchun joy
    for row, amount, pct in zip(rows, amounts, shares(amounts), strict=True):
        ax.annotate(
            f"{format_short(amount)} · {pct}%",
            (amount, row),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            fontsize=9,
            color=MUTED,
        )
    ax.set_title("Kategoriyalar", loc="left", fontsize=11, color=TEXT, pad=8)


def _timeline(ax, buckets: list[tuple[date, int]], granularity: Granularity) -> None:
    positions = range(len(buckets))
    ax.bar(positions, [amount for _, amount in buckets], width=0.7, color=BAR)
    step = max(1, len(buckets) // 10)  # ko'pi bilan ~10 ta yorliq
    ticks = list(positions)[::step]
    ax.set_xticks(ticks, [bucket_label(buckets[i][0], granularity) for i in ticks])
    ax.yaxis.set_major_locator(MaxNLocator(4))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: format_short(int(v)) if v else "0"))
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    titles = {Granularity.DAY: "Kunlar", Granularity.WEEK: "Haftalar", Granularity.MONTH: "Oylar"}
    ax.set_title(titles[granularity], loc="left", fontsize=11, color=TEXT, pad=8)


def render_chart(
    period: Period,
    categories: list[CategoryTotal],
    buckets: list[tuple[date, int]],
    granularity: Granularity,
) -> bytes:
    """categories bo'sh bo'lmasligi kerak. Vaqt grafigi faqat 2+ guruh bo'lsa chiziladi."""
    with_timeline = len(buckets) > 1
    bar_rows = len(fold_categories(categories))
    cat_height = 0.9 + 0.38 * bar_rows
    heights = [cat_height, 2.6] if with_timeline else [cat_height]

    fig = Figure(figsize=(WIDTH_IN, sum(heights) + 0.7), facecolor=SURFACE)
    fig.suptitle(f"Chiqim · {format_period(period)}", x=0.02, ha="left", fontsize=13, color=TEXT)
    axes = fig.subplots(len(heights), 1, gridspec_kw={"height_ratios": heights}, squeeze=False)
    for (ax,) in axes:
        _style(ax)
    _categories(axes[0][0], categories)
    if with_timeline:
        _timeline(axes[1][0], buckets, granularity)

    fig.tight_layout()
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=DPI, facecolor=SURFACE)
    return buffer.getvalue()
