"""Bugungi sanani foydalanuvchi vaqt mintaqasida olish.

Server UTC'da ishlasa ham, Toshkentda 00:30 bo'lsa "bugun" Toshkent bo'yicha hisoblanadi.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo


def today_in(tz: ZoneInfo) -> date:
    return datetime.now(tz).date()
