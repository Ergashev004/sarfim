import pytest

from bot.services.categories import DEFAULT_CATEGORIES, FALLBACK_CATEGORY
from bot.services.categorizer import KEYWORDS, categorize, is_income, match_custom


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
        ("uzi 150000", "Sog'liq"),
        ("uziga 150000", "Sog'liq"),
        ("УЗИ 150000", "Sog'liq"),
        ("analiz topshirdim 80000", "Sog'liq"),
        ("o'yinchoq 60000", "Sovg'alar"),  # "o'yin" (Ko'ngilochar) emas — uzunroq o'zak
        ("o'yinchoqqa 60000", "Sovg'alar"),
        ("oyinchoq 60000", "Sovg'alar"),
        ("игрушка 60000", "Sovg'alar"),
        ("tabrik 20000", "Sovg'alar"),
        ("tabriklash uchun 20000", "Sovg'alar"),
        ("kartochka 10000", "Sovg'alar"),
        ("o'yin 50000", "Ko'ngilochar"),  # qisqasi o'z kategoriyasida qoladi
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
        "o'yinchoq va kino 90000",  # uzun o'zak ham boshqa so'zdagi kategoriyani bekor qilmaydi
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


# ---------------------------------------------------------------------------
# Shaxsiy kategoriya nomi matnda
# ---------------------------------------------------------------------------

CUSTOM = ["Ikkinchi ish", "Cs", "Baliq ovi"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Ikkinchi ishdagilar bilan cafe 600000", "Ikkinchi ish"),
        ("ikkinchi ish uchun", "Ikkinchi ish"),
        ("ikkinchi non 5000", None),  # "ish" yo'q
        ("ish joyiga taksi", None),  # "ikkinchi" yo'q
        ("cs 70k", "Cs"),
        ("CSga 70000", "Cs"),  # qisqa nom + qo'shimcha
        ("csv fayl", None),  # qisqa nom prefiks bo'yicha mos kelmaydi
        ("Counter strike 70k", None),  # nom matnda yo'q — AI'ga
        ("baliq ovi uchun qarmoq", "Baliq ovi"),
        ("ИККИНЧИ ИШ", None),  # kirill nom lotin matnga mos emas — normal holat
    ],
)
def test_match_custom(text, expected):
    assert match_custom(text, CUSTOM) == expected


def test_match_custom_prefers_more_specific_name():
    assert match_custom("cs turnir 50000", ["Cs", "Cs turnir"]) == "Cs turnir"


def test_match_custom_tie_is_ambiguous():
    assert match_custom("cs dota 50000", ["Cs", "Dota"]) is None


def test_match_custom_empty():
    assert match_custom("cs 5000", []) is None
