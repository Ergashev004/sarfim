"""Baza modellari. Pul har doim butun son (BigInteger), qoldiq saqlanmaydi."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from bot.db.base import Base


class TransactionType(StrEnum):
    EXPENSE = "expense"
    INCOME = "income"


class TransactionSource(StrEnum):
    KEYWORD = "keyword"
    AI = "ai"
    MANUAL = "manual"


def _str_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    # Bazada VARCHAR + CHECK, qiymat sifatida enum.value saqlanadi
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=16,
        values_callable=lambda e: [m.value for m in e],
    )


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    first_name: Mapped[str | None] = mapped_column(String(64))
    timezone: Mapped[str] = mapped_column(
        String(64), default="Asia/Tashkent", server_default="Asia/Tashkent"
    )
    created_at: Mapped[datetime] = _created_at()


class Category(Base):
    """user_id NULL — standart kategoriya. Barcha kategoriyalar faqat xarajat uchun."""

    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("user_id", "name"),
        # UNIQUE NULL'larni bir-biriga teng deb hisoblamaydi, standartlar uchun alohida indeks
        Index(
            "uq_categories_default_name",
            "name",
            unique=True,
            sqlite_where=text("user_id IS NULL"),
            postgresql_where=text("user_id IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(32))
    emoji: Mapped[str | None] = mapped_column(String(8))


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(
            "(type = 'expense' AND category_id IS NOT NULL)"
            " OR (type = 'income' AND category_id IS NULL)",
            name="category_matches_type",
        ),
        Index("ix_transactions_user_id_occurred_on", "user_id", "occurred_on"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[TransactionType] = mapped_column(_str_enum(TransactionType, "transaction_type"))
    amount: Mapped[int] = mapped_column(BigInteger)  # so'm; USD bo'lsa sentlarda
    currency: Mapped[str] = mapped_column(String(3), default="UZS", server_default="UZS")
    # RESTRICT: kategoriya o'chirilishidan oldin yozuvlar "Boshqa"ga o'tkaziladi (servisda)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT")
    )
    note: Mapped[str | None] = mapped_column(Text)
    occurred_on: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = _created_at()
    source: Mapped[TransactionSource] = mapped_column(
        _str_enum(TransactionSource, "transaction_source")
    )


class UserKeyword(Base):
    """Foydalanuvchi kategoriyani tuzatganda bot o'sha so'zni eslab qoladi."""

    __tablename__ = "user_keywords"
    __table_args__ = (UniqueConstraint("user_id", "keyword"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    keyword: Mapped[str] = mapped_column(String(64))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))


class AiRequest(Base):
    """AI so'rovlari jurnali: debug va xarajatni kuzatish uchun."""

    __tablename__ = "ai_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    input_text: Mapped[str] = mapped_column(Text)
    response: Mapped[str | None] = mapped_column(Text)
    tokens_in: Mapped[int | None]
    tokens_out: Mapped[int | None]
    latency_ms: Mapped[int | None]
    success: Mapped[bool]
    created_at: Mapped[datetime] = _created_at()
