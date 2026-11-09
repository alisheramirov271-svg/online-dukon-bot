
import asyncio
import os
import sqlite3

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from dotenv import load_dotenv


# TOKEN
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN topilmadi! .env faylni tekshiring.")


# BOT
bot = Bot(token=TOKEN)
dp = Dispatcher()

TZ = ZoneInfo("Asia/Tashkent")
DB_NAME = "database.db"


# FSM HOLATLARI
class Plan(StatesGroup):
    date = State()
    time = State()
    title = State()
    reminder = State()


# ASOSIY MENYU
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Reja qo‘shish")],
        [KeyboardButton(text="📅 Bugungi rejalar")],
        [KeyboardButton(text="📆 Ertangi rejalar")],
        [KeyboardButton(text="✏️ Rejani tahrirlash")],
        [KeyboardButton(text="🗑 Rejani o‘chirish")]
    ],
    resize_keyboard=True
)


# ESLATMA VARIANTLARI
reminder_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔔 Faqat bir marta")],
        [KeyboardButton(text="5 daqiqada")],
        [KeyboardButton(text="10 daqiqada")],
        [KeyboardButton(text="15 daqiqada")],
        [KeyboardButton(text="30 daqiqada")],
        [KeyboardButton(text="1 soatda")]
    ],
    resize_keyboard=True
)


REMINDER_OPTIONS = {
    "🔔 Faqat bir marta": 0,
    "5 daqiqada": 5,
    "10 daqiqada": 10,
    "15 daqiqada": 15,
    "30 daqiqada": 30,
    "1 soatda": 60
}


# DATABASE
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            due_time TEXT NOT NULL,
            last_reminded TEXT,
            completed INTEGER DEFAULT 0,
            reminder_minutes INTEGER DEFAULT 10
        )
    """)

    # Eski database uchun yangi ustun qo‘shish
    cursor.execute("PRAGMA table_info(plans)")
    columns = [column[1] for column in cursor.fetchall()]

    if "reminder_minutes" not in columns:
        cursor.execute("""
            ALTER TABLE plans
            ADD COLUMN reminder_minutes INTEGER DEFAULT 10
        """)

    conn.commit()
    conn.close()


# START
@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()

    await message.answer(
        "Assalomu alaykum! 👋\n\n"
        "Shaxsiy reja va eslatma botiga xush kelibsiz!\n\n"
        "Kerakli bo‘limni tanlang:",
        reply_markup=main_keyboard
    )


# REJA QO‘SHISH
@dp.message(F.text == "➕ Reja qo‘shish")
async def add_plan(message: Message, state: FSMContext):
    await state.clear()

    await state.set_state(Plan.date)

    await message.answer(
        "📅 Reja sanasini kiriting.\n\n"
        "Masalan: 10.11.2026",
        reply_markup=ReplyKeyboardRemove()
    )


# SANANI QABUL QILISH
@dp.message(Plan.date)
async def get_date(message: Message, state: FSMContext):
    try:
        date = datetime.strptime(message.text.strip(), "%d.%m.%Y")

        if date.date() < datetime.now(TZ).date():
            await message.answer("❌ O‘tgan sanani kiritmang.")
            return

        await state.update_data(date=message.text.strip())
        await state.set_state(Plan.time)

        await message.answer(
            "⏰ Reja vaqtini kiriting.\n\n"
            "Masalan: 14:30"
        )

    except ValueError:
        await message.answer(
            "❌ Sana noto‘g‘ri!\n"
            "Masalan: 10.11.2026"
        )


# VAQTNI QABUL QILISH
@dp.message(Plan.time)
async def get_time(message: Message, state: FSMContext):
    try:
        datetime.strptime(message.text.strip(), "%H:%M")

        await state.update_data(time=message.text.strip())
        await state.set_state(Plan.title)

        await message.answer("📝 Reja nomini kiriting:")

    except ValueError:
        await message.answer(
            "❌ Vaqt noto‘g‘ri!\n"
            "Masalan: 14:30"
        )


# REJA NOMINI QABUL QILISH
@dp.message(Plan.title)
async def get_title(message: Message, state: FSMContext):
    title = (message.text or "").strip()

    if not title:
        await message.answer("Reja nomini yozing.")
        return

    await state.update_data(title=title)
    await state.set_state(Plan.reminder)

    await message.answer(
        "🔔 Eslatma oralig‘ini tanlang:\n\n"
        "Tanlangan vaqt bo‘yicha bot sizga eslatib turadi.",
        reply_markup=reminder_keyboard
    )


# ESLATMA VAQTINI TANLASH
@dp.message(Plan.reminder)
async def get_reminder(message: Message, state: FSMContext):
    reminder_minutes = REMINDER_OPTIONS.get(message.text)

    if reminder_minutes is None:
        await message.answer(
            "Iltimos, tayyor variantlardan birini tanlang.",
            reply_markup=reminder_keyboard
        )
        return

    data = await state.get_data()

    due_time = datetime.strptime(
        data["date"] + " " + data["time"],
        "%d.%m.%Y %H:%M"
    ).replace(tzinfo=TZ)

    if due_time <= datetime.now(TZ):
        await message.answer(
            "❌ Bu vaqt o‘tib ketgan. Rejani qaytadan kiriting.",
            reply_markup=main_keyboard
        )
        await state.clear()
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO plans
        (chat_id, title, due_time, reminder_minutes)
        VALUES (?, ?, ?, ?)
    """, (
        message.chat.id,
        data["title"],
        due_time.isoformat(),
        reminder_minutes
    ))

    conn.commit()
    conn.close()

    if reminder_minutes == 0:
        reminder_text = "Faqat bir marta"
    else:
        reminder_text = f"Har {reminder_minutes} daqiqada"

    await message.answer(
        "✅ Rejangiz saqlandi!\n\n"
        f"📝 Reja: {data['title']}\n"
        f"📅 Sana: {data['date']}\n"
        f"⏰ Vaqt: {data['time']}\n"
        f"🔔 Eslatma: {reminder_text}",
        reply_markup=main_keyboard
    )

    await state.clear()


# REJALARNI KO‘RISH
async def show_plans(message: Message, day_offset: int):
    today = datetime.now(TZ).date()
    target_day = today + timedelta(days=day_offset)

    start = datetime.combine(
        target_day,
        datetime.min.time(),
        tzinfo=TZ
    )

    end = start + timedelta(days=1)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title, due_time, completed
        FROM plans
        WHERE chat_id = ?
        AND due_time >= ?
        AND due_time < ?
        ORDER BY due_time
    """, (
        message.chat.id,
        start.isoformat(),
        end.isoformat()
    ))

    plans = cursor.fetchall()
    conn.close()

    if not plans:
        await message.answer(
            "📭 Bu kun uchun rejalar mavjud emas.",
            reply_markup=main_keyboard
        )
        return

    text = "📋 Rejalaringiz:\n\n"

    for plan in plans:
        plan_id, title, due_time, completed = plan
        plan_time = datetime.fromisoformat(due_time)

        status = "✅ Bajarildi" if completed else "⏳ Kutilmoqda"

        text += (
            f"📝 {title}\n"
            f"⏰ {plan_time.strftime('%H:%M')}\n"
            f"{status}\n\n"
        )

    await message.answer(text, reply_markup=main_keyboard)


@dp.message(F.text == "📅 Bugungi rejalar")
async def today_plans(message: Message):
    await show_plans(message, 0)


@dp.message(F.text == "📆 Ertangi rejalar")
async def tomorrow_plans(message: Message):
    await show_plans(message, 1)


# REJANI TAHRIRLASH
@dp.message(F.text == "✏️ Rejani tahrirlash")
async def edit_plan_menu(message: Message):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title, due_time
        FROM plans
        WHERE chat_id = ? AND completed = 0
        ORDER BY due_time
    """, (message.chat.id,))

    plans = cursor.fetchall()
    conn.close()

    if not plans:
        await message.answer("📭 Tahrirlash uchun rejalar mavjud emas.")
        return

    buttons = []

    for plan_id, title, due_time in plans:
        plan_date = datetime.fromisoformat(due_time)

        buttons.append([
            InlineKeyboardButton(
                text=f"✏️ {title} — {plan_date.strftime('%d.%m %H:%M')}",
                callback_data=f"edit:{plan_id}"
            )
        ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(
        "Qaysi rejani tahrirlamoqchisiz?",
        reply_markup=keyboard
    )


@dp.callback_query(F.data.startswith("edit:"))
async def edit_plan_start(callback: CallbackQuery, state: FSMContext):
    plan_id = int(callback.data.split(":")[1])

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT title, due_time
        FROM plans
        WHERE id = ? AND chat_id = ? AND completed = 0
    """, (plan_id, callback.message.chat.id))

    plan = cursor.fetchone()
    conn.close()

    if not plan:
        await callback.answer("Reja topilmadi.", show_alert=True)
        return

    await state.clear()
    await state.update_data(edit_id=plan_id)

    await state.set_state(Plan.date)

    await callback.message.answer(
        f"✏️ Eski reja: {plan[0]}\n\n"
        "Yangi sanani kiriting (DD.MM.YYYY):"
    )

    await callback.answer()


# TAHRIRLASH UCHUN SANA
@dp.message(Plan.date)
async def edit_get_date(message: Message, state: FSMContext):
    # Bu handler avvalgi get_date bilan to‘qnashishi mumkin.
    pass

# REJANI O‘CHIRISH
@dp.message(F.text == "🗑 Rejani o‘chirish")
async def delete_plan_menu(message: Message):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title, due_time
        FROM plans
        WHERE chat_id = ? AND completed = 0
        ORDER BY due_time
    """, (message.chat.id,))

    plans = cursor.fetchall()
    conn.close()

    if not plans:
        await message.answer("📭 O‘chirish uchun rejalar mavjud emas.")
        return

    buttons = []

    for plan_id, title, due_time in plans:
        plan_date = datetime.fromisoformat(due_time)

        buttons.append([
            InlineKeyboardButton(
                text=f"🗑 {title} — {plan_date.strftime('%d.%m %H:%M')}",
                callback_data=f"delete:{plan_id}"
            )
        ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(
        "Qaysi rejani o‘chirmoqchisiz?",
        reply_markup=keyboard
    )


@dp.callback_query(F.data.startswith("delete:"))
async def delete_plan(callback: CallbackQuery):
    plan_id = int(callback.data.split(":")[1])

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM plans
        WHERE id = ? AND chat_id = ?
    """, (plan_id, callback.message.chat.id))

    deleted = cursor.rowcount

    conn.commit()
    conn.close()

    if deleted:
        await callback.message.edit_text("✅ Reja muvaffaqiyatli o‘chirildi!")
        await callback.answer("O‘chirildi!")
    else:
        await callback.answer("Reja topilmadi.", show_alert=True)

# BAJARILDI TUGMASI
@dp.callback_query(F.data.startswith("done:"))
async def complete_plan(callback: CallbackQuery):
    plan_id = int(callback.data.split(":")[1])

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE plans
        SET completed = 1
        WHERE id = ? AND chat_id = ?
    """, (plan_id, callback.message.chat.id))

    conn.commit()
    conn.close()

    await callback.answer("Reja bajarildi! ✅")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("✅ Reja bajarildi!")


# ESLATMALARNI TEKSHIRISH
async def reminder_loop():
    while True:
        now = datetime.now(TZ)

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, chat_id, title, due_time,
                   last_reminded, reminder_minutes
            FROM plans
            WHERE completed = 0
        """)

        plans = cursor.fetchall()
        conn.close()

        for plan in plans:
            (
                plan_id,
                chat_id,
                title,
                due_time,
                last_reminded,
                reminder_minutes
            ) = plan

            due = datetime.fromisoformat(due_time)

            if now < due:
                continue

            should_send = False

            if last_reminded is None:
                should_send = True

            elif reminder_minutes > 0:
                last = datetime.fromisoformat(last_reminded)

                if now - last >= timedelta(minutes=reminder_minutes):
                    should_send = True

            if should_send:
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="✅ Bajarildi",
                                callback_data=f"done:{plan_id}"
                            )
                        ]
                    ]
                )

                try:
                    await bot.send_message(
                        chat_id,
                        f"🔔 ESLATMA!\n\n"
                        f"📝 Rejangiz: {title}\n\n"
                        "Rejani bajarishni unutmang!",
                        reply_markup=keyboard
                    )

                    conn = sqlite3.connect(DB_NAME)
                    cursor = conn.cursor()

                    cursor.execute("""
                        UPDATE plans
                        SET last_reminded = ?
                        WHERE id = ?
                    """, (now.isoformat(), plan_id))

                    conn.commit()
                    conn.close()

                except Exception as error:
                    print("Eslatma yuborishda xato:", error)

        await asyncio.sleep(30)


# BOTNI ISHGA TUSHIRISH
async def main():
    init_db()

    reminder_task = asyncio.create_task(reminder_loop())

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print("Bot ishga tushdi!")

        await dp.start_polling(bot)

    finally:
        reminder_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
