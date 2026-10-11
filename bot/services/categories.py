"""Standart kategoriyalar va ular bilan bog'liq cheklovlar."""

from typing import Final

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
