"""/kategoriyalar: ro'yxat, shaxsiy kategoriya qo'shish va o'chirish."""

from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import repo
from bot.db.models import User
from bot.keyboards.categories import (
    CategoryAction,
    cancel_keyboard,
    delete_confirm_keyboard,
    manage_keyboard,
)
from bot.services.card import category_label
from bot.services.categories import (
    CUSTOM_EMOJI,
    FALLBACK_CATEGORY,
    NAME_MAX_LEN,
    NAME_MIN_LEN,
    clean_category_name,
    render_category_list,
    validate_category_name,
)

router = Router(name="categories")

ASK_NAME = (
    f"Yangi kategoriya nomini yozing ({NAME_MIN_LEN}–{NAME_MAX_LEN} belgi).\n"
    "Masalan: <code>Sport</code>"
)
NOT_FOUND = "Kategoriya topilmadi yoki allaqachon o'chirilgan."
CANCELLED = "Bekor qilindi."


class CategoryForm(StatesGroup):
    name = State()


async def _overview(session: AsyncSession, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    categories = await repo.list_categories(session, user_id)
    standard = [(c.name, c.emoji) for c in categories if c.user_id is None]
    custom = [c for c in categories if c.user_id is not None]
    text = render_category_list(standard, [(c.name, c.emoji) for c in custom])
    markup = manage_keyboard([(c.id, category_label(c.name, c.emoji)) for c in custom])
    return text, markup


async def _edit(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


@router.message(Command("kategoriyalar"))
async def cmd_categories(
    message: Message, session: AsyncSession, db_user: User, state: FSMContext | None = None
) -> None:
    # Faqat nom kutilayotgan bo'lsa bekor qilamiz — saqlanmagan xarajat yo'qolmasin
    if state is not None and await state.get_state() == CategoryForm.name.state:
        await state.clear()
    text, markup = await _overview(session, db_user.id)
    await message.answer(text, reply_markup=markup)


@router.message(CategoryForm.name, F.text, ~F.text.startswith("/"))
async def on_category_name(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User
) -> None:
    name = clean_category_name(message.text)
    categories = await repo.list_categories(session, db_user.id)
    custom_count = sum(1 for c in categories if c.user_id is not None)
    error = validate_category_name(name, [c.name for c in categories], custom_count)
    if error is not None:
        await message.answer(error, reply_markup=cancel_keyboard())  # nomni qayta kutamiz
        return

    await repo.add_custom_category(session, db_user.id, name, CUSTOM_EMOJI)
    await session.commit()
    await state.clear()
    await message.answer(f"✅ «{escape(name, quote=False)}» kategoriyasi qo'shildi.")
    text, markup = await _overview(session, db_user.id)
    await message.answer(text, reply_markup=markup)


@router.callback_query(CategoryAction.filter())
async def on_category_action(
    callback: CallbackQuery,
    callback_data: CategoryAction,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    match callback_data.action:
        case "add":
            await state.set_state(CategoryForm.name)
            await callback.message.answer(ASK_NAME, reply_markup=cancel_keyboard())

        case "cancel":
            await state.clear()
            await _edit(callback, CANCELLED, None)

        case "del":
            category = await repo.get_own_custom_category(
                session, db_user.id, callback_data.category_id
            )
            if category is None:
                await callback.answer(NOT_FOUND, show_alert=True)
                return
            count = await repo.count_category_transactions(session, db_user.id, category.id)
            name = escape(category.name, quote=False)
            text = f"«{name}» o'chirilsinmi?"
            if count:
                text += f"\nUnga tegishli {count} ta yozuv «{FALLBACK_CATEGORY}»ga o'tadi."
            await _edit(callback, text, delete_confirm_keyboard(category.id))

        case "delok":
            fallback = await repo.get_default_category(session, FALLBACK_CATEGORY)
            category = await repo.get_own_custom_category(
                session, db_user.id, callback_data.category_id
            )
            moved = await repo.delete_custom_category(
                session, db_user.id, callback_data.category_id, fallback.id
            )
            if moved is None:
                await callback.answer(NOT_FOUND, show_alert=True)
                return
            await session.commit()
            text = f"🗑 «{escape(category.name, quote=False)}» o'chirildi."
            if moved:
                text += f"\n{moved} ta yozuv «{FALLBACK_CATEGORY}»ga o'tdi."
            await _edit(callback, text, None)

    await callback.answer()
