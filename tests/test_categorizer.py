import pytest

from bot.services.categories import DEFAULT_CATEGORIES, FALLBACK_CATEGORY
from bot.services.categorizer import KEYWORDS, categorize, is_income


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("taksi 30000", "Transport"),
        ("taksiga 30000", "Transport"),  # qo'shimcha
        ("taksida ketdim", "Transport"),
        ("такси 20 минг", "Transport"),  # kirill
        ("Yandex 18000", "Transport"),  # katta harf
        ("yo'lkira 2000", "Transport"),
        ("yoʻlkira 2000", "Transport"),  # boshqa apostrof
        ("non 5000", "Oziq-ovqat"),
        ("nonga 5000", "Oziq-ovqat"),  # qisqa o'zak + qo'shimcha
        ("нон 5000", "Oziq-ovqat"),
        ("korzinkadan 150k", "Oziq-ovqat"),
        ("gazga 100000", "Uy/kommunal"),
        ("svet 80000", "Uy/kommunal"),
        ("internet 99000", "Aloqa/internet"),
        ("krossovka 400k", "Kiyim"),
        ("dorixona 45000", "Sog'liq"),
        ("аптека 30000", "Sog'liq"),
        ("kurs uchun 500k", "Ta'lim"),
        ("kino 40000", "Ko'ngilochar"),
        ("oshxona 35000", "Kafe/restoran"),
        ("osh 35000", "Kafe/restoran"),
        ("sovg'a 100k", "Sovg'alar"),
        ("gul 50000", "Sovg'alar"),
    ],
)
def test_category_found(text, expected):
    assert categorize(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "30000",  # so'z yo'q
        "nimadir 30000",  # lug'atda yo'q
        "nonushta 15000",  # "non" qisqa o'zak — "nonushta" uni anglatmaydi
        "gazeta 3000",  # "gaz" emas
        "unga 5000",  # "un" (ol mahsuloti) lug'atda yo'q, "unga" = "u kishiga"
        "taksi non 20000",  # ikki kategoriya — noaniq, tugmalar chiqadi
    ],
)
def test_category_not_found(text):
    assert categorize(text) is None


def test_keywords_cover_all_defaults_except_fallback():
    names = {name for name, _ in DEFAULT_CATEGORIES} - {FALLBACK_CATEGORY}
    assert set(KEYWORDS) == names


@pytest.mark.parametrize(
    "text",
    ["+5 mln", "+ 500000", "oylik 5 mln", "oyligim keldi 5 mln", "maosh 4 mln", "Stipendiya 800k",
     "pul keldi 200k", "kirim 100000", "ойлик 5 млн", "маош 3 млн"],
)  # fmt: skip
def test_income_detected(text):
    assert is_income(text)


@pytest.mark.parametrize("text", ["taksi 30000", "5000 + 3000 non", "kino 40000"])
def test_not_income(text):
    assert not is_income(text)
