"""scripts/eval_ai.py: throttling va 429 da qayta urinish (tarmoqsiz)."""

import pytest

from scripts import eval_ai
from tests.fakes import FakeAi
from tests.test_gemini import QUOTA, RETRY_INFO, _api_error


@pytest.fixture
def clock() -> dict[str, float]:
    return {"now": 1000.0}


@pytest.fixture
def sleeps(monkeypatch, clock) -> list[float]:
    """asyncio.sleep o'rniga: kutishlar yoziladi, vaqt soxta soat bilan suriladi."""
    recorded: list[float] = []

    async def fake_sleep(delay):
        recorded.append(round(delay, 3))
        clock["now"] += delay

    monkeypatch.setattr(eval_ai.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(eval_ai.time, "monotonic", lambda: clock["now"])
    return recorded


async def _call(client, rpm=15):
    return await eval_ai.complete_with_retry(
        client, eval_ai.Throttle(rpm), system="", prompt="", schema={}
    )


async def test_throttle_spaces_requests(sleeps):
    throttle = eval_ai.Throttle(rpm=15)
    for _ in range(3):
        await throttle.wait()
    assert sleeps == [4.0, 4.0]  # 60/15


async def test_retries_after_retry_delay(sleeps):
    client = FakeAi(_api_error(429, [QUOTA, RETRY_INFO]), {"category": None, "amount": 0})
    reply, _ = await _call(client)
    assert reply.text == '{"category": null, "amount": 0}'
    assert len(client.calls) == 2
    assert 23.0 in sleeps


async def test_fallback_delay_without_retry_info(sleeps):
    client = FakeAi(_api_error(429), {"category": None, "amount": 0})
    await _call(client)
    assert eval_ai.FALLBACK_DELAY_S in sleeps


async def test_gives_up_after_three_retries(sleeps):
    client = FakeAi(*[_api_error(429, [RETRY_INFO])] * 4)
    with pytest.raises(Exception, match="429"):
        await _call(client)
    assert len(client.calls) == 1 + eval_ai.MAX_RETRIES


async def test_other_errors_not_retried(sleeps):
    client = FakeAi(_api_error(400), {"category": None, "amount": 0})
    with pytest.raises(Exception, match="400"):
        await _call(client)
    assert len(client.calls) == 1


class SlowAi(FakeAi):
    """Har chaqiruv soxta soatda API_S soniya oladi."""

    API_S = 0.7

    def __init__(self, clock, *replies) -> None:
        super().__init__(*replies)
        self.clock = clock

    async def complete(self, **kwargs):
        self.clock["now"] += self.API_S
        return await super().complete(**kwargs)


async def test_latency_excludes_throttle_and_retry_waits(sleeps, clock):
    throttle = eval_ai.Throttle(rpm=15)
    client = SlowAi(clock, *[{"category": None, "amount": 0}] * 2)
    latencies = []
    for _ in range(2):
        _, latency = await eval_ai.complete_with_retry(
            client, throttle, system="", prompt="", schema={}
        )
        latencies.append(latency)
    assert 3.3 in sleeps  # throttle kutdi (4.0 - 0.7)...
    assert latencies == [pytest.approx(0.7)] * 2  # ...lekin kechikishga kirmadi

    client = SlowAi(clock, _api_error(429, [RETRY_INFO]), {"category": None, "amount": 0})
    _, latency = await eval_ai.complete_with_retry(
        client, throttle, system="", prompt="", schema={}
    )
    assert 23.0 in sleeps
    assert latency == pytest.approx(0.7)  # faqat muvaffaqiyatli urinish


def test_error_text_is_short():
    text = eval_ai.short(_api_error(429, [RETRY_INFO] * 20))
    assert len(text) == eval_ai.ERROR_TEXT_LEN
    assert text.startswith("ClientError: 429")


async def test_accuracy_counts_only_answered(sleeps, monkeypatch, tmp_path):
    csv_path = tmp_path / "eval.csv"
    csv_path.write_text(
        "text,category,amount\ntaksi 1000,Transport,\nmanikyur 1000,,\nkino 1000,Ko'ngilochar,\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(eval_ai, "DATASET", csv_path)
    client = FakeAi(
        {"category": "Transport", "amount": 1000},
        {"category": "Kiyim", "amount": 1000},  # noto'g'ri
        *[_api_error(429)] * 4,  # javob olinmadi
    )
    stats = await eval_ai.run(client, "test-model", rpm=60)
    assert (stats.total, stats.answered, stats.cat_ok) == (3, 2, 1)
    assert len(stats.errors) == 1 and "429" in stats.errors[0]
    assert stats.latencies == [0.0, 0.0]  # FakeAi soxta soatni surmaydi; throttle 1 s kutgan
