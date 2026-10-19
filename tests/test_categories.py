from aiogram.filters import Command

from bot.db import repo
from bot.db.models import Category
from bot.handlers.categories import cmd_categories
from bot.handlers.start import build_welcome_text
from bot.keyboards.menu import MENU_CATEGORIES, main_menu
from bot.services.categories import (
    DEFAULT_CATEGORIES,
    FALLBACK_CATEGORY,
    keyword_examples,
    render_category_list,
)


class FakeMessage:
    def __init__(self) -> None:
        self.answers: list[str] = []

    async def answer(self, text, **_):
        self.answers.append(text)


def test_examples_are_latin_and_unique():
    examples = keyword_examples("Oziq-ovqat")
    assert examples == ["non", "sut", "go'sht", "bozor"]  # "gosht" takrorlanmaydi
    assert all(w.isascii() for w in keyword_examples("Transport"))


def test_fallback_has_no_examples():
    assert keyword_examples(FALLBACK_CATEGORY) == []


def test_list_shows_all_default_categories():
    text = render_category_list(list(DEFAULT_CATEGORIES), [])
    for name, emoji in DEFAULT_CATEGORIES:
        assert f"{emoji} {name}" in text
    assert "taksi" in text
    assert "&#x27;" not in text  # apostrof o'qiladigan holda qoladi
    assert "Shaxsiy kategoriyalar: 0/3" in text


def test_list_shows_custom_categories_escaped():
    text = render_category_list(list(DEFAULT_CATEGORIES), [("Mashina", None), ("<b>x</b>", "🐟")])
    assert "Shaxsiy kategoriyalar: 2/3" in text
    assert "\nMashina" in text
    assert "🐟 &lt;b&gt;x&lt;/b&gt;" in text


async def test_command_lists_own_and_default_only(session):
    me = await repo.get_or_create_user(session, 1, None)
    other = await repo.get_or_create_user(session, 2, None)
    session.add_all(
        [Category(user_id=me.id, name="Mashina"), Category(user_id=other.id, name="Baliq")]
    )
    await session.commit()

    message = FakeMessage()
    await cmd_categories(message, session, me)

    [text] = message.answers
    assert all(name in text for name, _ in DEFAULT_CATEGORIES)
    assert "Mashina" in text
    assert "Baliq" not in text
    assert "1/3" in text


def test_command_registered_and_mentioned_in_welcome():
    from bot.handlers.categories import router

    commands = [
        f.callback
        for handler in router.message.handlers
        for f in handler.filters or []
        if isinstance(f.callback, Command)
    ]
    assert commands and "kategoriyalar" in commands[0].commands
    # /start matni pastki menyuga yo'naltiradi, menyuda kategoriyalar tugmasi bor
    assert "kategoriyalar" in build_welcome_text("Akobir")
    assert MENU_CATEGORIES in [b.text for row in main_menu().keyboard for b in row]
