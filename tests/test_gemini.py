"""Gemini klienti: tarmoqsiz, SDK chaqiruvi almashtirilgan."""

import asyncio
from types import SimpleNamespace

import pytest

from bot.services.gemini import GeminiClient


def _client(monkeypatch, fake) -> GeminiClient:
    client = GeminiClient("test-key", "gemini-test", timeout_s=0.1)
    monkeypatch.setattr(client._client.aio.models, "generate_content", fake)
    return client


async def test_returns_text_and_tokens(monkeypatch):
    seen = {}

    async def fake(*, model, contents, config):
        seen.update(model=model, contents=contents, config=config)
        usage = SimpleNamespace(prompt_token_count=100, candidates_token_count=12)
        return SimpleNamespace(text='{"category": "Transport", "amount": 0}', usage_metadata=usage)

    reply = await _client(monkeypatch, fake).complete(
        system="sys", prompt="matn", schema={"type": "object"}
    )
    assert reply.text == '{"category": "Transport", "amount": 0}'
    assert (reply.tokens_in, reply.tokens_out) == (100, 12)
    assert seen["model"] == "gemini-test"
    assert seen["config"].response_mime_type == "application/json"
    assert seen["config"].response_json_schema == {"type": "object"}
    assert seen["config"].system_instruction == "sys"


async def test_empty_response(monkeypatch):
    async def fake(**_):
        return SimpleNamespace(text=None, usage_metadata=None)

    reply = await _client(monkeypatch, fake).complete(system="", prompt="", schema={})
    assert (reply.text, reply.tokens_in) == ("", None)


async def test_hanging_request_times_out(monkeypatch):
    async def fake(**_):
        await asyncio.sleep(10)

    monkeypatch.setattr("bot.services.gemini.GRACE_S", 0.0)
    with pytest.raises(TimeoutError):
        await _client(monkeypatch, fake).complete(system="", prompt="", schema={})
