"""Botni ishga tushirish: uv run python -m bot.main"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.commands import set_bot_commands
from bot.config import get_settings
from bot.db.session import make_engine, make_sessionmaker
from bot.handlers import categories, entry, start
from bot.middlewares.db import DbMiddleware


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    engine = make_engine(settings.database_url)
    dp = Dispatcher(tz=settings.tz)  # tz handler'larga parametr sifatida uzatiladi
    dp.update.middleware(DbMiddleware(make_sessionmaker(engine)))
    # entry oxirida: u har qanday matnni oladi
    dp.include_routers(start.router, categories.router, entry.router)

    try:
        # Bot o'chiq paytida kelgan eski xabarlarni o'tkazib yuboramiz
        await bot.delete_webhook(drop_pending_updates=True)
        await set_bot_commands(bot)
        await dp.start_polling(bot)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
