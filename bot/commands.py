"""Telegram menyusidagi buyruqlar ("/" bosilganda chiqadigan ro'yxat).

Yangi buyruq qo'shilsa shu yerga ham yoziladi — test handler'lar bilan mosligini tekshiradi.
"""

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeDefault

BOT_COMMANDS: list[BotCommand] = [
    BotCommand(command="start", description="Botni ishga tushirish"),
    BotCommand(command="kategoriyalar", description="Barcha kategoriyalar ro'yxati"),
]


async def set_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(BOT_COMMANDS, scope=BotCommandScopeDefault())
