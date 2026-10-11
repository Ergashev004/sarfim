"""Standart kategoriyalar va ular bilan bog'liq cheklovlar."""

from html import escape
from typing import Final

from bot.services.card import category_label
from bot.services.categorizer import KEYWORDS

# (nom, emoji) — tartib tugmalarda ham shu tartibda chiqadi
DEFAULT_CATEGORIES: Final[tuple[tuple[str, str], ...]] = (
    ("Oziq-ovqat", "🛒"),
    ("Transport", "🚕"),
    ("Uy/kommunal", "🏠"),
    ("Aloqa/internet", "📱"),
    ("Kiyim", "👕"),
    ("Sog'liq", "💊"),
    ("Ta'lim", "📚"),
    ("Ko'ngilochar", "🎬"),
    ("Kafe/restoran", "🍽"),
    ("Sovg'alar", "🎁"),
    ("Boshqa", "📦"),
)

FALLBACK_CATEGORY: Final = "Boshqa"  # shaxsiy kategoriya o'chirilsa yozuvlar shu yerga o'tadi
MAX_CUSTOM_CATEGORIES: Final = 3

EXAMPLES_PER_CATEGORY: Final = 4


def keyword_examples(name: str, limit: int = EXAMPLES_PER_CATEGORY) -> list[str]:
    """Lug'atdan bir nechta lotincha misol; "go'sht"/"gosht" kabi variantlar bir marta."""
    seen: set[str] = set()
    result: list[str] = []
    for word in KEYWORDS.get(name, ()):
        key = word.replace("'", "")
        if not word.isascii() or key in seen:
            continue  # kirill variantlari ko'rsatilmaydi
        seen.add(key)
        result.append(word)
        if len(result) == limit:
            break
    return result


def render_category_list(
    standard: list[tuple[str, str | None]], custom: list[tuple[str, str | None]]
) -> str:
    """/kategoriyalar matni. Elementlar: (nom, emoji)."""

    def line(name: str, emoji: str | None, examples: list[str]) -> str:
        label = escape(category_label(name, emoji), quote=False)
        return f"{label} — <i>{', '.join(examples)}…</i>" if examples else label

    lines = ["📂 <b>Kategoriyalar</b>", ""]
    lines += [line(name, emoji, keyword_examples(name)) for name, emoji in standard]
    lines += ["", f"<b>Shaxsiy kategoriyalar: {len(custom)}/{MAX_CUSTOM_CATEGORIES}</b>"]
    lines += [line(name, emoji, []) for name, emoji in custom]
    lines += ["", "Kategoriya aniqlanmasa, bot tugmalar orqali so'raydi."]
    return "\n".join(lines)
