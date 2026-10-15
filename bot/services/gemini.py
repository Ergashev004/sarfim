"""Google Gemini klienti (google-genai SDK). Faqat so'rov yuboradi, javobni tekshirmaydi."""

from __future__ import annotations

import asyncio
import re

from google import genai
from google.genai import errors, types

from bot.services.ai import AiReply

GRACE_S = 2.0  # HTTP timeout'dan keyingi umumiy chegara zaxirasi
# SDK HTTP timeout'ni serverga deadline sifatida yuboradi; Gemini 10 s dan kamini rad etadi (400).
# Foydalanuvchi uchun haqiqiy chegara — asyncio.wait_for (timeout_s + GRACE_S).
MIN_HTTP_TIMEOUT_S = 10.0

_DELAY_RE = re.compile(r"^(\d+(?:\.\d+)?)s$")  # google.rpc.RetryInfo: "23s", "1.5s"


def is_rate_limited(error: BaseException) -> bool:
    """429 RESOURCE_EXHAUSTED — so'rovlar limiti (free tier: daqiqasiga N ta)."""
    return isinstance(error, errors.APIError) and error.code == 429


def retry_delay_s(error: BaseException) -> float | None:
    """429 javobidagi retryDelay (soniya). Topilmasa None."""
    if not is_rate_limited(error) or not isinstance(error.details, dict):
        return None
    details = error.details.get("error", error.details).get("details") or []
    for item in details:
        if isinstance(item, dict) and str(item.get("@type", "")).endswith("RetryInfo"):
            m = _DELAY_RE.match(str(item.get("retryDelay", "")))
            if m:
                return float(m.group(1))
    return None


class GeminiClient:
    def __init__(self, api_key: str, model: str, timeout_s: float) -> None:
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(max(timeout_s, MIN_HTTP_TIMEOUT_S) * 1000)),
        )
        self._model = model
        self._timeout_s = timeout_s

    async def complete(self, *, system: str, prompt: str, schema: dict) -> AiReply:
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema,
            temperature=0,
        )
        # HTTP timeout'dan tashqari umumiy chegara: SDK qayta urinsa ham bot kutib qolmaydi
        response = await asyncio.wait_for(
            self._client.aio.models.generate_content(
                model=self._model, contents=prompt, config=config
            ),
            timeout=self._timeout_s + GRACE_S,
        )
        usage = response.usage_metadata
        return AiReply(
            text=response.text or "",
            tokens_in=usage.prompt_token_count if usage else None,
            tokens_out=usage.candidates_token_count if usage else None,
        )
