"""Testlar uchun soxta obyektlar: Telegram xabari/tugmasi, FSM, AI klienti."""

import json
from zoneinfo import ZoneInfo

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.services.ai import AiReply
from bot.services.resolver import AiGateway


class FakeMessage:
    def __init__(self, text: str | None = None) -> None:
        self.text = text
        self.answers: list[tuple[str, object]] = []
        self.edits: list[tuple[str, object]] = []
        self.markups: list[object] = []

    async def answer(self, text, reply_markup=None, **_):
        self.answers.append((text, reply_markup))

    async def edit_text(self, text, reply_markup=None, **_):
        self.edits.append((text, reply_markup))

    async def edit_reply_markup(self, reply_markup=None, **_):
        self.markups.append(reply_markup)


class FakeCallback:
    def __init__(self) -> None:
        self.message = FakeMessage()
        self.alerts: list[str | None] = []

    async def answer(self, text=None, show_alert=False, **_):
        self.alerts.append(text)


def make_state(user_id: int) -> FSMContext:
    """Har chaqiruvda yangi xotira — boshqa foydalanuvchining holati bo'sh."""
    return FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=user_id, user_id=user_id))


class FakeAi:
    """Javoblar navbat bilan qaytadi; Exception bo'lsa — ko'tariladi."""

    def __init__(self, *replies) -> None:
        self.replies = list(replies)
        self.calls: list[dict] = []

    async def complete(self, *, system: str, prompt: str, schema: dict) -> AiReply:
        self.calls.append({"system": system, "prompt": prompt, "schema": schema})
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        if isinstance(reply, dict):
            reply = json.dumps(reply)
        return AiReply(text=reply, tokens_in=120, tokens_out=15)


def gateway(*replies, limit: int = 50) -> tuple[AiGateway, FakeAi]:
    client = FakeAi(*replies)
    return AiGateway(client=client, daily_limit=limit, tz=ZoneInfo("Asia/Tashkent")), client
