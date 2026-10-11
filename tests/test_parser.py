from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
import time_machine

from bot.services.clock import today_in
from bot.services.parser import (
    AmountStatus,
    DateStatus,
    parse_amount,
    parse_date,
)

# ---------------------------------------------------------------------------
# Summa: muvaffaqiyatli holatlar
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("taksi 30000", 30_000),
        ("taksi 30 000", 30_000),
        ("taksi 30k", 30_000),
        ("taksi 30 k", 30_000),
        ("taksi 30K", 30_000),
        ("taksi 30к", 30_000),  # kirillcha "к"
        ("taksi 30 ming", 30_000),
        ("taksiga 30 mingga", 30_000),  # o'zbekcha qo'shimcha
        ("15 ming 300 non", 15_300),
        ("1 mln 200 ming", 1_200_000),
        ("15,300 non", 15_300),  # vergul + 3 raqam = minglik
        ("15.300 non", 15_300),
        ("15,3 ming", 15_300),  # ko'paytiruvchi bilan = kasr
        ("15.3k", 15_300),  # float bo'lsa 15299 chiqardi
        ("1.5 mln", 1_500_000),
        ("1,5 mln", 1_500_000),
        ("1.500.000", 1_500_000),
        ("1 500 000", 1_500_000),
        ("+5000000 oylik", 5_000_000),
        ("kirim 500000", 500_000),
        ("1000000000", 1_000_000_000),  # chegara: aynan 1 mlrd ruxsat
        ("1 mlrd", 1_000_000_000),
        ("taksi-30000", 30_000),  # chiziqcha so'zga yopishgan, minus emas
        ("taksi 30 000", 30_000),  # bank SMS'idagi qattiq bo'shliq
    ],
)
def test_amount_ok(text, expected):
    result = parse_amount(text)
    assert result.status is AmountStatus.OK
    assert result.value == expected
    assert result.rounded is False


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("15300,50", 15_301),  # yarim tiyin yuqoriga
        ("15300.4", 15_300),
        ("15300,49", 15_300),
    ],
)
def test_amount_with_tiyin_is_rounded(text, expected):
    result = parse_amount(text)
    assert result.status is AmountStatus.OK
    assert result.value == expected
    assert result.rounded is True


# ---------------------------------------------------------------------------
# Summa: rad etiladigan va noaniq holatlar
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["0", "taksi 0", "-500", "taksi -500", "1000000001", "2 mlrd", "0,4"],
)
def test_amount_invalid(text):
    result = parse_amount(text)
    assert result.status is AmountStatus.INVALID
    assert result.value is None
    assert result.reason


@pytest.mark.parametrize("text", ["taksi", "", "   ", "ming so'm"])
def test_amount_missing(text):
    assert parse_amount(text).status is AmountStatus.MISSING


@pytest.mark.parametrize("text", ["2 ta non 5000", "30k 5000", "taksi 20000 ovqat 45000"])
def test_amount_multiple_goes_to_ai(text):
    assert parse_amount(text).status is AmountStatus.MULTIPLE


# ---------------------------------------------------------------------------
# Sana
# ---------------------------------------------------------------------------

TODAY = date(2026, 10, 11)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("bugun taksi 30000", date(2026, 10, 11)),
        ("kecha taksi 30000", date(2026, 10, 10)),
        ("kechagi ovqat 45k", date(2026, 10, 10)),
        ("o'tgan kuni taksi 20000", date(2026, 10, 9)),
        ("oʻtgan kuni taksi 20000", date(2026, 10, 9)),  # boshqa apostrof
        ("5-oktabr taksi 30000", date(2026, 10, 5)),
        ("5 oktyabrda taksi 30000", date(2026, 10, 5)),
        ("05.10 taksi 30000", date(2026, 10, 5)),
        ("5/10 taksi 30000", date(2026, 10, 5)),
        ("05.10.2026 taksi 30000", date(2026, 10, 5)),
        ("05.10.26 taksi 30000", date(2026, 10, 5)),
        ("11.09 taksi", date(2026, 9, 11)),  # aynan 30 kun oldin - ruxsat
    ],
)
def test_date_ok(text, expected):
    result = parse_date(text, TODAY)
    assert result.status is DateStatus.OK
    assert result.value == expected


def test_date_not_written_means_today():
    result = parse_date("taksi 30000", TODAY)
    assert result.status is DateStatus.NOT_FOUND
    assert result.value == TODAY


@pytest.mark.parametrize(
    ("text", "status"),
    [
        ("10.09 taksi", DateStatus.TOO_OLD),  # 31 kun oldin
        ("1-avgust taksi", DateStatus.TOO_OLD),
        ("12.10.2026 taksi", DateStatus.FUTURE),  # yil bilan yozilgan ertangi kun
        ("31.02 taksi", DateStatus.INVALID),
    ],
)
def test_date_rejected(text, status):
    result = parse_date(text, TODAY)
    assert result.status is status
    assert result.value is None


def test_date_without_year_never_goes_to_future():
    # 12.10 bu yil kelajak, shuning uchun o'tgan yil deb olinadi -> 30 kundan eski
    assert parse_date("12.10 taksi", TODAY).status is DateStatus.TOO_OLD


def test_year_boundary():
    # 3-yanvarda "28.12" yozilsa - o'tgan yilning 28-dekabri
    result = parse_date("28.12 taksi", date(2027, 1, 3))
    assert result.value == date(2026, 12, 28)


def test_date_is_removed_before_amount_parsing():
    # "05.10" summa emas: sana olib tashlangach faqat 30000 qoladi
    result = parse_date("05.10 taksi 30000", TODAY)
    amount = parse_amount(result.rest)
    assert amount.status is AmountStatus.OK
    assert amount.value == 30_000


def test_amount_like_15_300_is_not_a_date():
    result = parse_date("non 15.300", TODAY)
    assert result.status is DateStatus.NOT_FOUND
    assert parse_amount(result.rest).value == 15_300


@pytest.mark.parametrize(
    ("text", "expected"),
    [("taksi 12.5k", 12_500), ("1.5 mln oylik", 1_500_000), ("2,5 ming non", 2_500)],
)
def test_decimal_with_multiplier_is_not_a_date(text, expected):
    # Regressiya: "12.5k" avval 12-may sanasi deb o'qilardi
    result = parse_date(text, TODAY)
    assert result.status is DateStatus.NOT_FOUND
    assert parse_amount(result.rest).value == expected


def test_kecha_word_is_not_k_multiplier():
    result = parse_date("kecha 30000", TODAY)
    assert parse_amount(result.rest).value == 30_000


# ---------------------------------------------------------------------------
# Vaqt mintaqasi: server UTC'da, foydalanuvchi Toshkentda
# ---------------------------------------------------------------------------

TASHKENT = ZoneInfo("Asia/Tashkent")


@time_machine.travel(datetime(2026, 10, 10, 19, 30, tzinfo=UTC), tick=False)
def test_today_after_midnight_in_tashkent():
    # UTC bo'yicha hali 10-oktabr 19:30, Toshkentda esa 11-oktabr 00:30
    assert today_in(TASHKENT) == date(2026, 10, 11)


@time_machine.travel(datetime(2026, 10, 10, 18, 59, tzinfo=UTC), tick=False)
def test_today_before_midnight_in_tashkent():
    assert today_in(TASHKENT) == date(2026, 10, 10)
