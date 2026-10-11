from zoneinfo import ZoneInfo

from bot.config import Settings


def test_defaults_to_tashkent_timezone():
    settings = Settings(bot_token="test-token", _env_file=None)
    assert settings.tz == ZoneInfo("Asia/Tashkent")


def test_token_is_hidden_in_repr():
    settings = Settings(bot_token="super-secret", _env_file=None)
    assert "super-secret" not in repr(settings)
    assert settings.bot_token.get_secret_value() == "super-secret"
