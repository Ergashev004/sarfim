"""Gemini klienti: tarmoqsiz, SDK chaqiruvi almashtirilgan."""

import asyncio
from types import SimpleNamespace

import pytest

from bot.services.gemini import MIN_HTTP_TIMEOUT_S, GeminiClient


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


def _api_error(code: int, details: list | None = None):
    from google.genai import errors

    body = {"error": {"code": code, "status": "RESOURCE_EXHAUSTED", "message": "quota"}}
    if details is not None:
        body["error"]["details"] = details
    return (errors.ClientError if code < 500 else errors.ServerError)(code, body)


RETRY_INFO = {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "23s"}
QUOTA = {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": []}


@pytest.mark.parametrize(
    ("error", "limited", "delay"),
    [
        (_api_error(429, [QUOTA, RETRY_INFO]), True, 23.0),
        (_api_error(429, [{**RETRY_INFO, "retryDelay": "1.5s"}]), True, 1.5),
        (_api_error(429, [QUOTA]), True, None),
        (_api_error(429), True, None),
        (_api_error(400, [RETRY_INFO]), False, None),
        (_api_error(503, [RETRY_INFO]), False, None),
        (TimeoutError(), False, None),
    ],
)
def test_rate_limit_detection(error, limited, delay):
    from bot.services.gemini import is_rate_limited, retry_delay_s

    assert is_rate_limited(error) is limited
    assert retry_delay_s(error) == delay


async def test_rate_limit_error_propagates(monkeypatch):
    """Klient 429 ni yutmaydi — qaror qabul qilish chaqiruvchida (bot: tugmalar, eval: retry)."""
    from google.genai import errors

    async def fake(**_):
        raise _api_error(429, [RETRY_INFO])

    with pytest.raises(errors.ClientError):
        await _client(monkeypatch, fake).complete(system="", prompt="", schema={})


def test_http_timeout_not_below_server_minimum():
    # 5 s yuborilsa Gemini: "Minimum allowed deadline is 10s" (400)
    client = GeminiClient("test-key", "gemini-test", timeout_s=5.0)
    assert client._client._api_client._http_options.timeout == MIN_HTTP_TIMEOUT_S * 1000
    assert client._timeout_s == 5.0  # foydalanuvchi kutadigan chegara o'zgarmaydi
