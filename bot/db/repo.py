"""Bazaga so'rovlar. Funksiyalar commit qilmaydi — buni chaqiruvchi hal qiladi.

Yozuvga tegadigan har bir so'rov `user_id` bo'yicha ham filtrlanadi:
callback_data dagi ID'ga ishonilmaydi.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Category, Transaction, TransactionSource, TransactionType, User


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
