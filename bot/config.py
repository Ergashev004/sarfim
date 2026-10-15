"""Sozlamalar .env faylidan o'qiladi. Token kodda saqlanmaydi."""

from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: SecretStr  # SecretStr: logda yoki xatoda token ochiq ko'rinmaydi
    timezone: str = "Asia/Tashkent"
    log_level: str = "INFO"
    database_url: str = "sqlite+aiosqlite:///sarfim.db"

    # AI ixtiyoriy: kalit bo'lmasa bot kalit so'zlar va tugmalar bilan ishlaydi
    gemini_api_key: SecretStr | None = None
    ai_model: str = "gemini-3.5-flash-lite"
    ai_timeout_s: float = 10.0  # + gemini.GRACE_S; Gemini javobi 1–15 s orasida o'zgaradi
    ai_daily_limit: int = 50  # bitta foydalanuvchi uchun kuniga

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


@lru_cache
def get_settings() -> Settings:
    return Settings()
