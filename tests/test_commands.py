import re
from unittest.mock import AsyncMock

from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommandScopeDefault

from bot.commands import BOT_COMMANDS, set_bot_commands
from bot.handlers import categories, entry, start

ROUTERS = [start.router, categories.router, entry.router]


def _handled_commands() -> set[str]:
    """Router'larda ro'yxatdan o'tgan barcha buyruqlar."""
    names: set[str] = set()
    for router in ROUTERS:
        for handler in router.message.handlers:
            for f in handler.filters or []:
                if isinstance(f.callback, CommandStart):
                    names.add("start")
                elif isinstance(f.callback, Command):
                    names.update(c for c in f.callback.commands if isinstance(c, str))
    return names


def test_menu_matches_handlers():
    """Menyuda ishlamaydigan buyruq yo'q, ishlaydigan buyruq menyudan tushib qolmagan."""
    assert {c.command for c in BOT_COMMANDS} == _handled_commands()


def test_commands_follow_telegram_rules():
    for c in BOT_COMMANDS:
        assert re.fullmatch(r"[a-z0-9_]{1,32}", c.command)
        assert 1 <= len(c.description) <= 256


async def test_set_bot_commands_calls_telegram():
    bot = AsyncMock()
    await set_bot_commands(bot)
    bot.set_my_commands.assert_awaited_once()
    args, kwargs = bot.set_my_commands.await_args
    assert args[0] == BOT_COMMANDS
    assert isinstance(kwargs["scope"], BotCommandScopeDefault)
