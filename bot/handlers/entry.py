"""Xarajat/kirim kiritish oqimi. Mantiq servislarda, bu yerda faqat Telegram."""

from dataclasses import replace
from datetime import date
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import repo
from bot.db.models import Category, Transaction, TransactionSource, TransactionType, User
from bot.keyboards.entry import (
    AiConfirm,
    PendingCategory,
    TxAction,
    ai_confirm_keyboard,
    card_keyboard,
    category_keyboard,
    date_keyboard,
)
from bot.services.card import (
    category_label,
    date_choices,
    format_amount,
    is_allowed_date,
    render_ai_confirm,
    render_card,
)
from bot.services.clock import today_in
from bot.services.entry import (
    AmountQuestion,
    Entry,
    EntryStatus,
    confirmed,
    parse_entry,
    rejected,
    with_amount,
    with_category,
)
from bot.services.resolver import AiGateway, learn_keyword, resolve

router = Router(name="entry")

NOT_FOUND = "Yozuv topilmadi yoki allaqachon bekor qilingan."
STALE = "Bu so'rov eskirgan — xarajatni qaytadan yozing."
CANCELLED = "↩️ Bekor qilindi — yozuv o'chirildi."
AI_CONFIRMED = "✅ Tasdiqlandi"
AI_REJECTED = "✏️ Tushunarli, summani o'zingiz yozing"

AMOUNT_QUESTIONS = {
    AmountQuestion.MISSING: "Summani yozing, masalan: <code>30000</code>",
    AmountQuestion.MULTIPLE: (
        "Matnda bir nechta raqam bor. Summani alohida yozing, masalan: <code>5000</code>"
    ),
    AmountQuestion.TWO_DATES: (
        "Matnda ikkita sana bor — qaysi raqam summa ekanini aniqlay olmadim.\n"
        "Summani alohida yozing, masalan: <code>30000</code>"
    ),
}


class EntryForm(StatesGroup):
    amount = State()
    category = State()
    confirm = State()  # AI topgan summa tasdiqlanishi kutilmoqda


# ---------------------------------------------------------------------------
# Yordamchilar
# ---------------------------------------------------------------------------


async def _category_buttons(session: AsyncSession, user_id: int) -> list[tuple[int, str]]:
    categories = await repo.list_categories(session, user_id)
    return [(c.id, category_label(c.name, c.emoji)) for c in categories]


async def build_card(
    session: AsyncSession, tx: Transaction, today: date, *, rounded: bool = False
) -> tuple[str, InlineKeyboardMarkup]:
    label = None
    if tx.category_id is not None:
        category = await session.get(Category, tx.category_id)
        label = category_label(category.name, category.emoji)
    text = render_card(
        kind=tx.type,
        amount=tx.amount,
        occurred_on=tx.occurred_on,
        today=today,
        category=label,
        balance=await repo.get_balance(session, tx.user_id),
        rounded=rounded,
        ai_category=tx.source is TransactionSource.AI and tx.type is TransactionType.EXPENSE,
    )
    markup = card_keyboard(tx.id, with_category=tx.type is TransactionType.EXPENSE)
    return text, markup


async def _save(
    session: AsyncSession, user: User, entry: Entry, category: Category | None
) -> Transaction:
    tx = await repo.add_transaction(
        session,
        user_id=user.id,
        kind=entry.kind,
        amount=entry.amount,
        occurred_on=entry.occurred_on,
        source=entry.source,
        category_id=category.id if category else None,
        note=entry.note,
    )
    await session.commit()
    return tx


async def _edit(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


async def _edit_markup(callback: CallbackQuery, markup: InlineKeyboardMarkup) -> None:
    try:
        await callback.message.edit_reply_markup(reply_markup=markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


async def process_entry(
    message: Message,
    entry: Entry,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    today: date,
    ai: AiGateway | None = None,
) -> None:
    entry = await resolve(session, db_user.id, entry, today, ai)
    await session.commit()  # ai_requests jurnali
    match entry.status:
        case EntryStatus.BAD_DATE | EntryStatus.BAD_AMOUNT:
            await message.answer(entry.reason)

        case EntryStatus.NEED_AMOUNT:
            await state.set_state(EntryForm.amount)
            await state.update_data(entry=entry.to_dict())
            await message.answer(AMOUNT_QUESTIONS[entry.question])

        case EntryStatus.CONFIRM_AI:
            await state.set_state(EntryForm.confirm)
            await state.update_data(entry=entry.to_dict())
            label = None
            if entry.category is not None:
                category = await repo.get_category_by_name(session, db_user.id, entry.category)
                label = category_label(category.name, category.emoji) if category else None
            await message.answer(
                render_ai_confirm(amount=entry.amount, category=label, kind=entry.kind),
                reply_markup=ai_confirm_keyboard(),
            )

        case EntryStatus.NEED_CATEGORY:
            await state.set_state(EntryForm.category)
            await state.update_data(entry=entry.to_dict())
            buttons = await _category_buttons(session, db_user.id)
            await message.answer(
                f"💸 {format_amount(entry.amount)} — qaysi kategoriyaga yozay?",
                reply_markup=category_keyboard(buttons),
            )

        case EntryStatus.READY:
            await state.clear()
            category = None
            if entry.kind is TransactionType.EXPENSE:
                category = await repo.get_category_by_name(session, db_user.id, entry.category)
                if category is None:  # masalan, shaxsiy kategoriya shu orada o'chirilgan
                    await process_entry(
                        message,
                        replace(entry, category=None, status=EntryStatus.NEED_CATEGORY),
                        state,
                        session,
                        db_user,
                        today,
                    )
                    return
            tx = await _save(session, db_user, entry, category)
            text, markup = await build_card(session, tx, today, rounded=entry.rounded)
            await message.answer(text, reply_markup=markup)


# ---------------------------------------------------------------------------
# Xabarlar
# ---------------------------------------------------------------------------

_not_command = ~F.text.startswith("/")


@router.message(EntryForm.amount, F.text, _not_command)
async def on_amount_reply(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    tz: ZoneInfo,
    ai: AiGateway | None = None,
) -> None:
    today = today_in(tz)
    data = await state.get_data()
    entry = with_amount(Entry.from_dict(data["entry"]), message.text)
    if entry is None:
        # Summa emas — yangi yozuv sifatida qabul qilamiz
        await state.clear()
        entry = parse_entry(message.text, today)
    elif entry.status is EntryStatus.BAD_AMOUNT:
        await message.answer(entry.reason)  # holat saqlanadi, summani qayta kutamiz
        return
    await process_entry(message, entry, state, session, db_user, today, ai)


@router.message(F.text, _not_command)
async def on_text(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    tz: ZoneInfo,
    ai: AiGateway | None = None,
) -> None:
    await state.clear()
    today = today_in(tz)
    entry = parse_entry(message.text, today)
    await process_entry(message, entry, state, session, db_user, today, ai)


# ---------------------------------------------------------------------------
# Tugmalar
# ---------------------------------------------------------------------------


@router.callback_query(PendingCategory.filter())
async def on_pending_category(
    callback: CallbackQuery,
    callback_data: PendingCategory,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    tz: ZoneInfo,
) -> None:
    # FSM foydalanuvchi bo'yicha saqlanadi: begona odam bossa, uning holati bo'sh bo'ladi
    raw = (await state.get_data()).get("entry")
    if await state.get_state() != EntryForm.category.state or raw is None:
        await callback.answer(STALE, show_alert=True)
        return
    category = await repo.get_category(session, db_user.id, callback_data.category_id)
    if category is None:
        await callback.answer("Bu kategoriyani tanlab bo'lmaydi.", show_alert=True)
        return

    await state.clear()
    today = today_in(tz)
    entry = with_category(Entry.from_dict(raw), category.name)
    await learn_keyword(session, db_user.id, entry.note, category.id, today)
    tx = await _save(session, db_user, entry, category)
    text, markup = await build_card(session, tx, today, rounded=entry.rounded)
    await _edit(callback, text, markup)
    await callback.answer()


@router.callback_query(AiConfirm.filter())
async def on_ai_confirm(
    callback: CallbackQuery,
    callback_data: AiConfirm,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    tz: ZoneInfo,
) -> None:
    raw = (await state.get_data()).get("entry")
    if await state.get_state() != EntryForm.confirm.state or raw is None:
        await callback.answer(STALE, show_alert=True)
        return
    entry = Entry.from_dict(raw)
    await state.clear()
    await callback.answer()
    await _edit(callback, AI_CONFIRMED if callback_data.ok else AI_REJECTED, None)
    entry = confirmed(entry) if callback_data.ok else rejected(entry)
    # Tasdiqdan keyin AI qayta chaqirilmaydi (ai=None): NEED_CATEGORY bo'lsa — tugmalar
    await process_entry(callback.message, entry, state, session, db_user, today_in(tz))


@router.callback_query(TxAction.filter())
async def on_tx_action(
    callback: CallbackQuery,
    callback_data: TxAction,
    session: AsyncSession,
    db_user: User,
    tz: ZoneInfo,
) -> None:
    today = today_in(tz)
    action = callback_data.action

    if action == "cancel":
        # DELETE ... WHERE id AND user_id: ikkinchi bosish yoki begona yozuv — shunchaki 0 qator
        deleted = await repo.delete_own_transaction(session, callback_data.tx_id, db_user.id)
        await session.commit()
        if not deleted:
            await callback.answer(NOT_FOUND, show_alert=True)
            return
        await _edit(callback, CANCELLED, None)
        await callback.answer("Bekor qilindi")
        return

    tx = await repo.get_own_transaction(session, callback_data.tx_id, db_user.id)
    if tx is None:
        await callback.answer(NOT_FOUND, show_alert=True)
        return
    is_expense = tx.type is TransactionType.EXPENSE

    match action:
        case "cat" if is_expense:
            buttons = await _category_buttons(session, db_user.id)
            await _edit_markup(callback, category_keyboard(buttons, tx.id))
        case "date":
            await _edit_markup(callback, date_keyboard(tx.id, date_choices(today)))
        case "back":
            await _edit_markup(callback, card_keyboard(tx.id, with_category=is_expense))
        case "setcat" if is_expense:
            category = await repo.get_category(session, db_user.id, callback_data.value)
            if category is None:
                await callback.answer("Bu kategoriyani tanlab bo'lmaydi.", show_alert=True)
                return
            tx.category_id = category.id
            tx.source = TransactionSource.MANUAL
            await learn_keyword(session, db_user.id, tx.note, category.id, today)
            await session.commit()
            await _edit(callback, *await build_card(session, tx, today))
        case "setdate":
            try:
                new_date = date.fromordinal(callback_data.value)
            except ValueError:
                new_date = None
            if new_date is None or not is_allowed_date(new_date, today):
                await callback.answer("Bu sanani tanlab bo'lmaydi.", show_alert=True)
                return
            tx.occurred_on = new_date
            await session.commit()
            await _edit(callback, *await build_card(session, tx, today))
        case "cat" | "setcat":  # kirim
            await callback.answer("Kirimga kategoriya berilmaydi.", show_alert=True)
            return
    await callback.answer()
