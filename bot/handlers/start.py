from html import escape

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router(name="start")


def build_welcome_text(first_name: str | None) -> str:
    # Ism HTML sifatida yuboriladi, shuning uchun < > & belgilarini xavfsizlantiramiz
    name = escape(first_name) if first_name else "do'stim"
    return (
        f"Salom, <b>{name}</b>! Men <b>Sarfim</b> — kirim-chiqimlaringizni hisoblab boraman.\n\n"
        "Xarajat yozing:  <code>taksi 30000</code>\n"
        "Kirim yozing:  <code>+5 mln oylik</code>\n"
        "Kategoriyalar:  /kategoriyalar\n"
        "Hisobot:  /hisobot\n"
        "Oxirgi yozuvlar:  /oxirgi"
    )


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    first_name = message.from_user.first_name if message.from_user else None
    await message.answer(build_welcome_text(first_name))
