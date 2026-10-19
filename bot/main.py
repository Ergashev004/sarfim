"""Botni ishga tushirish: uv run python -m bot.main"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.commands import set_bot_commands
from bot.config import get_settings
from bot.db.session import make_engine, make_sessionmaker
from bot.handlers import categories, entry, history, menu, report, start
from bot.middlewares.db import DbMiddleware
from bot.services.gemini import GeminiClient
from bot.services.resolver import AiGateway


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

    ai = None
    api_key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else ""
    if api_key:
        client = GeminiClient(api_key, settings.ai_model, settings.ai_timeout_s)
        ai = AiGateway(client=client, daily_limit=settings.ai_daily_limit, tz=settings.tz)
        logging.info("AI yoqilgan: %s", settings.ai_model)
    else:
        logging.info("GEMINI_API_KEY yo'q — AI o'chiq, faqat kalit so'zlar va tugmalar")

    # tz va ai handler'larga parametr sifatida uzatiladi
    dp = Dispatcher(tz=settings.tz, ai=ai)
    dp.update.middleware(DbMiddleware(make_sessionmaker(engine)))
    # menu boshida (tugma matni boshqasiga tushmasin), entry oxirida (har qanday matnni oladi)
    dp.include_routers(
        start.router, menu.router, categories.router, report.router, history.router, entry.router
    )

    try:
        # Bot o'chiq paytida kelgan eski xabarlarni o'tkazib yuboramiz
        await bot.delete_webhook(drop_pending_updates=True)
        await set_bot_commands(bot)
        await dp.start_polling(bot)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
