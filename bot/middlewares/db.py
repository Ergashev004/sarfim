from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.db.repo import get_or_create_user


class DbMiddleware(BaseMiddleware):
    """Har bir update uchun sessiya ochadi va foydalanuvchini bazaga yozadi (bor bo'lsa — topadi).

    Handler'lar `session` va `db_user` parametrlarini oladi.
    """

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self.sessionmaker = sessionmaker

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.sessionmaker() as session:
            data["session"] = session
            tg_user: User | None = data.get("event_from_user")
            if tg_user is not None:
                data["db_user"] = await get_or_create_user(session, tg_user.id, tg_user.first_name)
                await session.commit()
            return await handler(event, data)
