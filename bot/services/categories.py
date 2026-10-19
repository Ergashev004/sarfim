"""Standart kategoriyalar va ular bilan bog'liq cheklovlar."""

import re
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
CUSTOM_EMOJI: Final = "🏷"
NAME_MIN_LEN: Final = 2
NAME_MAX_LEN: Final = 32  # categories.name String(32)

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


def clean_category_name(text: str) -> str:
    """Ortiqcha bo'shliqlarni olib tashlaydi, birinchi harfni katta qiladi."""
    name = re.sub(r"\s+", " ", text).strip()
    return name[:1].upper() + name[1:]


def validate_category_name(name: str, existing: list[str], custom_count: int) -> str | None:
    """Xato matni yoki None (nom yaroqli). existing — foydalanuvchi ko'radigan barcha nomlar."""
    if custom_count >= MAX_CUSTOM_CATEGORIES:
        return f"Ko'pi bilan {MAX_CUSTOM_CATEGORIES} ta shaxsiy kategoriya qo'shish mumkin."
    if not NAME_MIN_LEN <= len(name) <= NAME_MAX_LEN:
        return f"Nom {NAME_MIN_LEN}–{NAME_MAX_LEN} belgidan iborat bo'lsin."
    if name.startswith("/") or not any(ch.isalpha() for ch in name):
        return "Nomda kamida bitta harf bo'lsin. Masalan: <code>Sport</code>"
    taken = next((e for e in existing if e.casefold() == name.casefold()), None)
    if taken is not None:
        return duplicate_name_error(taken)
    return None


def duplicate_name_error(taken: str) -> str:
    """taken — bazadagi mavjud nom (foydalanuvchi yozgani emas): standartmi yoki o'zinikimi."""
    emoji = dict(DEFAULT_CATEGORIES).get(taken)
    if emoji is not None:
        return (
            f"«{category_label(taken, emoji)}» — standart kategoriya, u allaqachon mavjud.\n"
            "Xarajatlarni shunga yozavering yoki boshqa nom tanlang."
        )
    name = escape(taken, quote=False)
    return f"Sizda «{name}» nomli kategoriya allaqachon mavjud.\nBoshqa nom yozing."


def validate_category_rename(name: str, existing: list[str], current: str) -> str | None:
    """Nomni o'zgartirish: limit tekshirilmaydi; eski nom (harf katta-kichigini o'zgartirish ham)
    "band" hisoblanmaydi."""
    others = [e for e in existing if e.casefold() != current.casefold()]
    return validate_category_name(name, others, custom_count=0)
