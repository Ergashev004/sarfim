from html import escape

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.keyboards.menu import main_menu

router = Router(name="start")


def build_welcome_text(first_name: str | None) -> str:
    # Ism HTML sifatida yuboriladi, shuning uchun < > & belgilarini xavfsizlantiramiz
    name = escape(first_name) if first_name else "do'stim"
    return (
        f"Salom, <b>{name}</b>! Men <b>Sarfim</b> — kirim-chiqimlaringizni hisoblab boraman.\n\n"
        "Xarajat yozing:  <code>taksi 25000</code>\n"
        "Kirim yozing:  <code>+5 mln oylik</code>\n\n"
        "Pastdagi menyuda — hisobotlar, oxirgi yozuvlar, sozlamalar va kategoriyalar.\n"
        "Tugma bosish shart emas: istalgan payt shunchaki yozing."
    )


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    first_name = message.from_user.first_name if message.from_user else None
    await message.answer(build_welcome_text(first_name), reply_markup=main_menu())
