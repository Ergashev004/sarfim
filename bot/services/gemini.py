"""Google Gemini klienti (google-genai SDK). Faqat so'rov yuboradi, javobni tekshirmaydi."""

from __future__ import annotations

import asyncio

from google import genai
from google.genai import types

from bot.services.ai import AiReply

GRACE_S = 2.0  # HTTP timeout'dan keyingi umumiy chegara zaxirasi


class GeminiClient:
    def __init__(self, api_key: str, model: str, timeout_s: float) -> None:
        self._client = genai.Client(
            api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout_s * 1000))
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
