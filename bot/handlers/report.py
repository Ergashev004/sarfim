"""/hisobot: davr tanlash, matn va grafik. Hisob-kitob repo (SQL) va services/report.py da."""

import asyncio
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import repo
from bot.db.models import User
from bot.keyboards.report import ReportPeriod, period_keyboard
from bot.services.chart import render_chart
from bot.services.clock import today_in
from bot.services.report import (
    RANGE_ERRORS,
    CategoryTotal,
    Period,
    PeriodKind,
    RangeStatus,
    ReportData,
    bucket_for,
    build_report_text,
    fill_buckets,
    fits_caption,
    parse_range,
    period_for,
    previous,
)

router = Router(name="report")

CHOOSE_PERIOD = "📊 Qaysi davr uchun hisobot?"
ASK_RANGE = (
    "Oraliqni yozing, masalan:\n"
    "<code>1.09 - 15.10</code>\n"
    "<code>1 sentabr - 15 oktabr</code>\n"
    "Bitta sana yozsangiz — faqat o'sha kun."
)


class ReportForm(StatesGroup):
    range = State()


async def send_report(
    message: Message, session: AsyncSession, user_id: int, period: Period
) -> None:
    income, expense = await repo.period_totals(session, user_id, period.start, period.end)
    before = previous(period)
    _, prev_expense = await repo.period_totals(session, user_id, before.start, before.end)
    rows = await repo.expense_by_category(session, user_id, period.start, period.end)
    data = ReportData(
        period=period,
        income=income,
        expense=expense,
        categories=[CategoryTotal(*row) for row in rows],
        prev_expense=prev_expense,
        balance=await repo.get_balance(session, user_id),
    )
    text = build_report_text(data)
    if not data.categories:  # chiqim yo'q — grafik ham yo'q
        await message.answer(text)
        return

    granularity = bucket_for(period)
    buckets = await repo.expense_by_bucket(session, user_id, period.start, period.end, granularity)
    buckets = fill_buckets(period, granularity, buckets)
    # matplotlib sinxron — event loop'ni to'xtatmaslik uchun alohida thread'da
    png = await asyncio.to_thread(render_chart, period, data.categories, buckets, granularity)
    photo = BufferedInputFile(png, filename="hisobot.png")
    if fits_caption(text):
        await message.answer_photo(photo, caption=text)
    else:
        await message.answer_photo(photo)
        await message.answer(text)


@router.message(Command("hisobot"))
async def cmd_report(message: Message, state: FSMContext | None = None) -> None:
    # Faqat oraliq kutilayotgan bo'lsa bekor qilamiz — saqlanmagan xarajat yo'qolmasin
    if state is not None and await state.get_state() == ReportForm.range.state:
        await state.clear()
    await message.answer(CHOOSE_PERIOD, reply_markup=period_keyboard())


@router.callback_query(ReportPeriod.filter())
async def on_period(
    callback: CallbackQuery,
    callback_data: ReportPeriod,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    tz: ZoneInfo,
) -> None:
    await callback.answer()  # grafik chizilguncha tugma "aylanib" turmasin
    if callback_data.kind is PeriodKind.CUSTOM:
        await state.set_state(ReportForm.range)
        await callback.message.answer(ASK_RANGE)
        return
    period = period_for(callback_data.kind, today_in(tz))
    await send_report(callback.message, session, db_user.id, period)


@router.message(ReportForm.range, F.text, ~F.text.startswith("/"))
async def on_range(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User, tz: ZoneInfo
) -> None:
    result = parse_range(message.text, today_in(tz))
    if result.status is RangeStatus.NO_DATES:
        # Sana yo'q — bu oraliq emas, oddiy yozuv: kiritish oqimiga o'tkazamiz
        await state.clear()
        raise SkipHandler
    if result.status is not RangeStatus.OK:
        await message.answer(RANGE_ERRORS[result.status])  # oraliqni qayta kutamiz
        return
    await state.clear()
    await send_report(message, session, db_user.id, result.period)
