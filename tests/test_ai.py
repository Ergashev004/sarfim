import json

import pytest

from bot.services.ai import (
    MAX_INPUT_LEN,
    UNKNOWN,
    AiAnswer,
    build_prompt,
    build_schema,
    parse_answer,
)
from bot.services.parser import MAX_AMOUNT

CATS = ["Oziq-ovqat", "Transport", "Sport"]


def _raw(category="Transport", amount=5000) -> str:
    return json.dumps({"category": category, "amount": amount})


def test_valid_answer():
    assert parse_answer(_raw(), CATS) == AiAnswer("Transport", 5000)


def test_custom_category_allowed():
    assert parse_answer(_raw("Sport"), CATS).category == "Sport"


@pytest.mark.parametrize(
    "category",
    [UNKNOWN, "Boshqa", "transport", "Kiyim", "", None, 5, ["Transport"]],
)
def test_category_outside_list_dropped(category):
    answer = parse_answer(_raw(category=category), CATS)
    assert answer == AiAnswer(None, 5000)


@pytest.mark.parametrize(
    "amount", [0, -5000, MAX_AMOUNT + 1, 5000.5, 5000.0, "5000", True, None, [5000]]
)
def test_bad_amount_dropped(amount):
    answer = parse_answer(_raw(amount=amount), CATS)
    assert answer == AiAnswer("Transport", None)


def test_max_amount_allowed():
    assert parse_answer(_raw(amount=MAX_AMOUNT), CATS).amount == MAX_AMOUNT


@pytest.mark.parametrize("raw", ["", "not json", "[1, 2]", '"Transport"', "null", None])
def test_broken_json_is_failure(raw):
    assert parse_answer(raw, CATS) is None


def test_missing_fields():
    assert parse_answer("{}", CATS) == AiAnswer(None, None)


def test_schema_limits_categories():
    schema = build_schema(CATS)
    assert schema["properties"]["category"]["enum"] == [*CATS, UNKNOWN]
    assert schema["properties"]["amount"]["type"] == "integer"
    assert set(schema["required"]) == {"category", "amount"}


def test_prompt_lists_categories_and_truncates_text():
    prompt = build_prompt("x" * 1000, CATS)
    assert all(f"- {c}" in prompt for c in CATS)
    assert "x" * MAX_INPUT_LEN in prompt
    assert "x" * (MAX_INPUT_LEN + 1) not in prompt
