from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import repo
from bot.db.models import User
from bot.services.categories import render_category_list

router = Router(name="categories")


@router.message(Command("kategoriyalar"))
async def cmd_categories(message: Message, session: AsyncSession, db_user: User) -> None:
    categories = await repo.list_categories(session, db_user.id)
    standard = [(c.name, c.emoji) for c in categories if c.user_id is None]
    custom = [(c.name, c.emoji) for c in categories if c.user_id is not None]
    await message.answer(render_category_list(standard, custom))
