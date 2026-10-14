"""Bazaga so'rovlar. Funksiyalar commit qilmaydi — buni chaqiruvchi hal qiladi.

Yozuvga tegadigan har bir so'rov `user_id` bo'yicha ham filtrlanadi:
callback_data dagi ID'ga ishonilmaydi.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import case, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import (
    AiRequest,
    Category,
    Transaction,
    TransactionSource,
    TransactionType,
    User,
    UserKeyword,
)


async def get_or_create_user(
    session: AsyncSession, telegram_id: int, first_name: str | None
) -> User:
    user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None:
        user = User(telegram_id=telegram_id, first_name=first_name)
        session.add(user)
        await session.flush()
    elif first_name and user.first_name != first_name:
        user.first_name = first_name
    return user


def _visible_to(user_id: int):
    return or_(Category.user_id.is_(None), Category.user_id == user_id)


async def list_categories(session: AsyncSession, user_id: int) -> list[Category]:
    """Standartlari birinchi, keyin foydalanuvchiniki."""
    stmt = (
        select(Category)
        .where(_visible_to(user_id))
        .order_by(Category.user_id.is_not(None), Category.id)
    )
    return list(await session.scalars(stmt))


async def get_category(session: AsyncSession, user_id: int, category_id: int) -> Category | None:
    """Faqat standart yoki shu foydalanuvchiniki bo'lsa qaytaradi."""
    stmt = select(Category).where(Category.id == category_id, _visible_to(user_id))
    return await session.scalar(stmt)


async def get_default_category(session: AsyncSession, name: str) -> Category | None:
    stmt = select(Category).where(Category.user_id.is_(None), Category.name == name)
    return await session.scalar(stmt)


async def get_category_by_name(session: AsyncSession, user_id: int, name: str) -> Category | None:
    """Standart yoki shu foydalanuvchining shaxsiy kategoriyasi (nomlar takrorlanmaydi)."""
    stmt = select(Category).where(Category.name == name, _visible_to(user_id))
    return await session.scalar(stmt)


# ---------------------------------------------------------------------------
# Shaxsiy kategoriyalar
# ---------------------------------------------------------------------------


async def count_custom_categories(session: AsyncSession, user_id: int) -> int:
    stmt = select(func.count()).select_from(Category).where(Category.user_id == user_id)
    return await session.scalar(stmt)


async def add_custom_category(
    session: AsyncSession, user_id: int, name: str, emoji: str | None
) -> Category:
    category = Category(user_id=user_id, name=name, emoji=emoji)
    session.add(category)
    await session.flush()
    return category


async def get_own_custom_category(
    session: AsyncSession, user_id: int, category_id: int
) -> Category | None:
    """Faqat shu foydalanuvchining shaxsiy kategoriyasi (standartlar o'chirilmaydi)."""
    stmt = select(Category).where(Category.id == category_id, Category.user_id == user_id)
    return await session.scalar(stmt)


async def count_category_transactions(session: AsyncSession, user_id: int, category_id: int) -> int:
    stmt = select(func.count()).where(
        Transaction.user_id == user_id, Transaction.category_id == category_id
    )
    return await session.scalar(stmt)


async def delete_custom_category(
    session: AsyncSession, user_id: int, category_id: int, fallback_id: int
) -> int | None:
    """Yozuvlarni fallback'ga o'tkazib, kategoriyani o'chiradi. O'tgan yozuvlar soni;
    kategoriya topilmasa (begona, standart yoki allaqachon o'chgan) — None.

    user_keywords dagi bog'liq so'zlar bazada CASCADE bilan o'chadi.
    """
    if await get_own_custom_category(session, user_id, category_id) is None:
        return None
    moved = await session.execute(
        update(Transaction)
        .where(Transaction.user_id == user_id, Transaction.category_id == category_id)
        .values(category_id=fallback_id)
    )
    await session.execute(
        delete(Category).where(Category.id == category_id, Category.user_id == user_id)
    )
    return moved.rowcount


# ---------------------------------------------------------------------------
# Foydalanuvchi kalit so'zlari
# ---------------------------------------------------------------------------


async def find_user_keyword_categories(
    session: AsyncSession, user_id: int, words: list[str]
) -> list[Category]:
    """Matndagi so'zlarga mos o'rganilgan kategoriyalar (takrorlanmasdan)."""
    if not words:
        return []
    stmt = (
        select(Category)
        .join(UserKeyword, UserKeyword.category_id == Category.id)
        .where(UserKeyword.user_id == user_id, UserKeyword.keyword.in_(words))
        .distinct()
    )
    return list(await session.scalars(stmt))


async def save_user_keyword(
    session: AsyncSession, user_id: int, keyword: str, category_id: int
) -> None:
    """Bor bo'lsa kategoriyasini yangilaydi, yo'q bo'lsa qo'shadi."""
    stmt = select(UserKeyword).where(UserKeyword.user_id == user_id, UserKeyword.keyword == keyword)
    row = await session.scalar(stmt)
    if row is None:
        session.add(UserKeyword(user_id=user_id, keyword=keyword, category_id=category_id))
    else:
        row.category_id = category_id
    await session.flush()


# ---------------------------------------------------------------------------
# AI jurnali
# ---------------------------------------------------------------------------


async def log_ai_request(
    session: AsyncSession,
    *,
    user_id: int,
    input_text: str,
    response: str | None,
    tokens_in: int | None,
    tokens_out: int | None,
    latency_ms: int,
    success: bool,
) -> None:
    session.add(
        AiRequest(
            user_id=user_id,
            input_text=input_text,
            response=response,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            success=success,
        )
    )
    await session.flush()


async def count_ai_requests_since(session: AsyncSession, user_id: int, since: datetime) -> int:
    """since — UTC, tz'siz (created_at bazada UTC'da saqlanadi)."""
    stmt = select(func.count()).where(AiRequest.user_id == user_id, AiRequest.created_at >= since)
    return await session.scalar(stmt)


async def add_transaction(
    session: AsyncSession,
    *,
    user_id: int,
    kind: TransactionType,
    amount: int,
    occurred_on: date,
    source: TransactionSource,
    category_id: int | None = None,
    note: str | None = None,
) -> Transaction:
    tx = Transaction(
        user_id=user_id,
        type=kind,
        amount=amount,
        occurred_on=occurred_on,
        source=source,
        category_id=category_id,
        note=note,
    )
    session.add(tx)
    await session.flush()
    return tx


async def get_own_transaction(
    session: AsyncSession, tx_id: int, user_id: int
) -> Transaction | None:
    stmt = select(Transaction).where(Transaction.id == tx_id, Transaction.user_id == user_id)
    return await session.scalar(stmt)


async def delete_own_transaction(session: AsyncSession, tx_id: int, user_id: int) -> bool:
    """O'chsa True. Yozuv yo'q (allaqachon o'chgan yoki begona) bo'lsa False — xato emas."""
    stmt = delete(Transaction).where(Transaction.id == tx_id, Transaction.user_id == user_id)
    result = await session.execute(stmt)
    return result.rowcount > 0


async def get_balance(session: AsyncSession, user_id: int) -> int | None:
    """Umumiy qoldiq = kirim − chiqim. Kirim umuman bo'lmasa None (qoldiq ko'rsatilmaydi)."""
    is_income = Transaction.type == TransactionType.INCOME
    stmt = select(
        func.coalesce(func.sum(case((is_income, Transaction.amount), else_=0)), 0),
        func.coalesce(func.sum(case((is_income, 0), else_=Transaction.amount)), 0),
        func.count().filter(is_income),
    ).where(Transaction.user_id == user_id)
    income, expense, income_count = (await session.execute(stmt)).one()
    if income_count == 0:
        return None
    return int(income) - int(expense)
