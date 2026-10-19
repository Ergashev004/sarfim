"""/oxirgi: oxirgi yozuvlar. Tugmalar bosilganda karta entry.on_tx_action orqali ochiladi."""

from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import repo
from bot.db.models import User
from bot.keyboards.entry import history_keyboard
from bot.services.clock import today_in
from bot.services.history import HISTORY_LIMIT, render_history

router = Router(name="history")


@router.message(Command("oxirgi"))
async def cmd_last(message: Message, session: AsyncSession, db_user: User, tz: ZoneInfo) -> None:
    rows = await repo.last_transactions(session, db_user.id, HISTORY_LIMIT)
    markup = history_keyboard([tx.id for tx, _ in rows]) if rows else None
    await message.answer(render_history(rows, today_in(tz)), reply_markup=markup)
