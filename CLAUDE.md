# Sarfim — loyiha qoidalari

Sarfim — shaxsiy kirim-chiqimni hisoblovchi Telegram bot (Python, aiogram 3).
Muallif: Akobir, QA muhandis. Foydalanuvchi bilan **o'zbek tilida** gaplash.
Kodni to'liq yoz, izohlar qisqa bo'lsin — uzun darslar kerak emas.

To'liq reja hujjati: https://claude.ai/code/artifact/aabe39af-c4d7-4511-9a60-b0e0b31b9a45

## Buyruqlar

```bash
uv run pytest                 # testlar
uv run ruff check . && uv run ruff format .
uv run alembic upgrade head   # bazani oxirgi migratsiyagacha yangilash
uv run python -m bot.main     # botni ishga tushirish
uv run python -m scripts.eval_ai [model] [--rpm 15]  # AI baholash (haqiqiy kalit, CI'ga kirmaydi)
```

Model o'zgarsa: `uv run alembic revision --autogenerate -m "..."`, so'ng faylni qo'lda tekshir
(`test_models_match_migrations` model va migratsiya farqini ushlaydi).

Kutubxona qo'shish faqat `uv add <paket>` (dev uchun `uv add --dev`). `pip` ishlatma.
Har bir o'zgarishdan keyin `pytest` va `ruff` yashil bo'lishi shart (CI ham shuni tekshiradi).

## Arxitektura

- `bot/services/` — Telegram'ga bog'liq bo'lmagan mantiq (parser, kategoriya, hisobot). Testlarning asosiy qismi shu yerda.
- `bot/handlers/`, `bot/keyboards/` — faqat Telegram qatlami, ichida biznes mantiq bo'lmaydi.
- `bot/db/` — SQLAlchemy 2 (async) + aiosqlite, migratsiyalar Alembic bilan.
  So'rovlar faqat `bot/db/repo.py` da; yozuvga tegadiganlari `user_id` bo'yicha ham filtrlanadi.
- Yangi buyruq qo'shilsa `bot/commands.py: BOT_COMMANDS` ga ham yoziladi ("/" menyusi; `test_commands` tekshiradi).
- Pastki menyu (`keyboards/menu.py`, /start yuboradi): tugma `handlers/menu.py` da mavjud handler'ni chaqiradi.
  `menu.router` boshqa router'lardan oldin turadi — aks holda tugma matni xarajat yoki kategoriya nomi deb o'qiladi.
- `bot/middlewares/db.py` — har update uchun sessiya + `db_user` (foydalanuvchi bazaga yoziladi).
- Kiritish: `services/entry.py: parse_entry()` → `Entry` (READY / NEED_CATEGORY / NEED_AMOUNT / BAD_*).
  Kategoriyasi noaniq yozuv tanlanguncha bazaga yozilmaydi (FSM xotirada, restartda yo'qoladi).
- `services/resolver.py: resolve()` — kategoriyani aniqlashtiradi: `user_keywords` → shaxsiy kategoriya nomi
  (`categorizer.match_custom`) → lug'at → AI.
  Bir nechta raqamda AI summa taklif qiladi → `CONFIRM_AI` (tasdiqsiz saqlanmaydi).
  Kategoriya qo'lda tanlansa/tuzatilsa `learn_keyword()` birinchi mazmunli so'zni eslab qoladi.
- AI: `services/ai.py` (prompt, JSON sxema, `parse_answer` — provayderga bog'liq emas),
  `services/gemini.py` (yagona provayder klienti). Handler'larga `ai: AiGateway | None` (kalit yo'q — None).
  Har so'rov `ai_requests` ga yoziladi; kunlik limit `AI_DAILY_LIMIT`, timeout `AI_TIMEOUT_S` (10 s; Gemini 10 s dan kam deadline'ni rad etadi).
  AI kutilayotganda handler `resolve(busy=...)` orqali "typing" yuboradi. Testlarda `tests/fakes.py: gateway()`.
- Hisobot: `services/report.py` (davr, oraliq, matn), `services/chart.py` (matplotlib, faqat `Figure`,
  handler'da `asyncio.to_thread`). Yig'indilar repo'da SQL bilan. Grafik: kategoriyalar gorizontal ustun
  (8 tadan ko'pi "Qolganlari"ga), pastida kun/hafta/oy ustunlari. Oraliq kutilayotganda sanasiz matn
  `SkipHandler` bilan kiritish oqimiga o'tadi.
- `/oxirgi` (`handlers/history.py`): raqamli tugma → `TxAction(open)` → oddiy karta (o'chirish, kategoriya, sana).
- Umumiy test fixture'lari (`me`, `stranger`, `state`, `frozen_time`) — `tests/conftest.py`.
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
  Tartib: `user_keywords` → shaxsiy kategoriya nomi matnda → standart kalit so'zlar (lug'at) → AI → tugmalar.
  Nomning har bir so'zi matnda bo'lishi kerak ("Ikkinchi ish" ← "ikkinchi ishdagilar", "ikkinchi non" emas). Foydalanuvchi o'rgatgan so'z
  lug'atdan ustun; bitta so'z qayta tuzatilsa eng oxirgisi qoladi (upsert). Matnda bir nechta
  o'rganilgan so'z turli kategoriyaga olib borsa — lug'atga o'tiladi.
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
- [x] 1b — baza modellari, Alembic, standart kategoriyalar (`bot/db/`, `bot/services/categories.py`)
- [x] 2 — kiritish oqimi (kalit so'zlar, karta, bekor qilish, kirim, qoldiq) + butun pipeline testlari
- [ ] 3 — AI (Gemini), user_keywords, ai_requests, shaxsiy kategoriyalar — kod va testlar tayyor;
      qoldi: haqiqiy kalit bilan `scripts.eval_ai`, model tanlash, Telegram'da smoke
- [ ] 4 — hisobotlar (SQL + matplotlib), /oxirgi — kod va testlar tayyor;
      qoldi: summani tahrirlash, Telegram'da smoke
- [ ] 5 — shaxsiy foydalanish, README, demo

Matnda ikkita sana bo'lsa (`5.10 kecha`) parser "kecha"ni oladi, `parse_entry` esa summani alohida so'raydi.
