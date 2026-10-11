# Sarfim — loyiha qoidalari

Sarfim — shaxsiy kirim-chiqimni hisoblovchi Telegram bot (Python, aiogram 3).
Muallif: Akobir, QA muhandis. Foydalanuvchi bilan **o'zbek tilida** gaplash.
Kodni to'liq yoz, izohlar qisqa bo'lsin — uzun darslar kerak emas.

To'liq reja hujjati: https://claude.ai/code/artifact/aabe39af-c4d7-4511-9a60-b0e0b31b9a45

## Buyruqlar

```bash
uv run pytest                 # testlar
uv run ruff check . && uv run ruff format .
uv run python -m bot.main     # botni ishga tushirish
```

Kutubxona qo'shish faqat `uv add <paket>` (dev uchun `uv add --dev`). `pip` ishlatma.
Har bir o'zgarishdan keyin `pytest` va `ruff` yashil bo'lishi shart (CI ham shuni tekshiradi).

## Arxitektura

- `bot/services/` — Telegram'ga bog'liq bo'lmagan mantiq (parser, kategoriya, hisobot). Testlarning asosiy qismi shu yerda.
- `bot/handlers/`, `bot/keyboards/` — faqat Telegram qatlami, ichida biznes mantiq bo'lmaydi.
- `bot/db/` — SQLAlchemy 2 (async) + aiosqlite, migratsiyalar Alembic bilan.
- Sozlamalar `.env` dan (`bot/config.py`, pydantic-settings). Token va kalitlar kodga yozilmaydi.

## Qat'iy qoidalar

- **Pul faqat `int`**, hech qachon `float`. So'm butun son; USD (keyinroq) sentlarda. Hisoblashda `Decimal`.
- **Vaqt mintaqasi `Asia/Tashkent`.** "Bugun" faqat `bot/services/clock.py: today_in()` orqali olinadi.
  Parser va servislar `today` ni parametr sifatida qabul qiladi — soatni o'zlari o'qimaydi.
- **Hisob-kitobni SQL qiladi, AI emas.** Qoldiq bazada saqlanmaydi, har safar `kirim − chiqim` hisoblanadi.
- **Har bir callback'da** yozuv shu foydalanuvchiga tegishli ekanini tekshir (callback_data dagi ID'ga ishonma).
- **AI javobi** har doim ruxsat etilgan kategoriyalar ro'yxati bilan solishtiriladi; AI topgan summa faqat tasdiqdan keyin saqlanadi.

## Biznes qoidalari

- Summa: 0 < summa ≤ 1 000 000 000. Tiyin (1–2 kasr raqam) eng yaqin so'mga yaxlitlanadi va kartada ko'rsatiladi.
  `15,300` / `15.300` = 15 300 (ajratgichdan keyin 3 raqam = minglik); ko'paytiruvchi bilan (`1,5 mln`, `15.3k`) — kasr.
- Matnda bir nechta raqam (`2 ta non 5000`) → AI'ga, natija tasdiqlanadi.
- Sana: oxirgi 30 kun (30-kun ham kiradi). Kelajak va eski sana rad etiladi. Yilsiz sana kelajakka tushsa — o'tgan yil.
- Avval sana parseri ishlaydi, keyin qolgan matndan summa olinadi.
- Kirim: boshida `+` yoki "oylik", "maosh", "stipendiya", "keldi", "kirim" so'zlari. Kirimga kategoriya berilmaydi.
- Xarajat kategoriyasi aniq bo'lsa darhol saqlanadi; kartada [Bekor qilish] [Kategoriya] [Sana].
  Aniq bo'lmasa: avval kalit so'zlar → `user_keywords` → AI → tugmalar.
- 11 ta standart kategoriya: Oziq-ovqat, Transport, Uy/kommunal, Aloqa/internet, Kiyim, Sog'liq, Ta'lim,
  Ko'ngilochar, Kafe/restoran, Sovg'alar, Boshqa. Foydalanuvchi ko'pi bilan 3 ta o'zinikini qo'sha oladi;
  o'chirilsa yozuvlari "Boshqa"ga o'tadi.
- Umumiy qoldiq har kartada (kirim bo'lmasa ko'rsatilmaydi), manfiy bo'lishi mumkin. Hisobotda davr farqi.
- Bekor qilish = yozuv bazadan butunlay o'chadi.

## Ma'lumotlar modeli

`users`, `categories` (user_id NULL = standart), `transactions` (type expense/income, amount bigint,
currency char(3)='UZS', category_id — xarajatda majburiy / kirimda NULL, CHECK bilan; note, occurred_on,
created_at, source keyword/ai/manual; indeks (user_id, occurred_on)), `user_keywords`, `ai_requests`.

## Roadmap holati

- [x] 0 — skelet, /start, CI
- [x] 1a — summa va sana parserlari (`bot/services/parser.py`, 73 test)
- [ ] 1b — baza modellari, Alembic, standart kategoriyalar
- [ ] 2 — kiritish oqimi (kalit so'zlar, karta, bekor qilish, kirim, qoldiq) + butun pipeline testlari
- [ ] 3 — AI, user_keywords, ai_requests, shaxsiy kategoriyalar
- [ ] 4 — hisobotlar (SQL + matplotlib), /oxirgi
- [ ] 5 — shaxsiy foydalanish, README, demo

Ma'lum cheklov: matnda ikkita sana bo'lsa (`5.10 kecha`) "kecha" ustun turadi, `5.10` summa bo'lib qoladi —
2-bosqichda bunday holatda summa so'raladigan qilinadi.
