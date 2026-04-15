# FINAL PRO Telegram Bot + FULL ADMIN PANEL

import logging
import sqlite3
import requests
import asyncio
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor

API_TOKEN = os.getenv("BOT_TOKEN")
CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

conn = sqlite3.connect('db.db')
cursor = conn.cursor()

# STATES
class DepositState(StatesGroup):
    amount = State()

class AdminAdd(StatesGroup):
    waiting = State()

class AdminEdit(StatesGroup):
    waiting = State()

# DB
cursor.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, balance REAL DEFAULT 0)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS numbers (id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT, price REAL)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS rentals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, number TEXT, expires_at INTEGER)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS payments (invoice_id TEXT, user_id INTEGER, amount REAL, status TEXT)''')
conn.commit()

# UI

def main_menu():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📱 Арендовать", callback_data="rent"))
    kb.add(InlineKeyboardButton("👤 Профиль", callback_data="profile"))
    return kb

# 💳 DEPOSIT FLOW (PREMIUM UX)

@dp.callback_query_handler(lambda c: c.data == "deposit")
async def deposit(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("0.5$", callback_data="dep_0.5"),
        InlineKeyboardButton("1$", callback_data="dep_1"),
        InlineKeyboardButton("5$", callback_data="dep_5"),
        InlineKeyboardButton("10$", callback_data="dep_10"),
        InlineKeyboardButton("✍️ Другая сумма", callback_data="dep_custom")
    )

    await call.message.answer(
        "💳 <b>Пополнение баланса</b>"
        "Выберите сумму или введите вручную:"
        "⚡ Минимум: 0.5$"
        "💰 Максимум: 500$",
        parse_mode="HTML",
        reply_markup=kb
    )

# QUICK AMOUNTS
@dp.callback_query_handler(lambda c: c.data.startswith("dep_") and c.data != "dep_custom")
async def quick_deposit(call: types.CallbackQuery):
    amount = float(call.data.split("_")[1])
    await process_payment(call.message, amount)

@dp.callback_query_handler(lambda c: c.data == "dep_custom")
async def custom_deposit(call: types.CallbackQuery):
    await DepositState.amount.set()
    await call.message.answer("💰 Введите сумму (0.5 - 500 USD):")

# PROCESS PAYMENT
async def process_payment(msg: types.Message, amount: float):
    if amount < 0.5 or amount > 500:
        return await msg.answer("❌ Неверная сумма")

    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN}

    r = requests.post(url, json={"asset": "USDT", "amount": amount}, headers=headers).json()

    invoice = r['result']
    pay_url = invoice['pay_url']
    invoice_id = invoice['invoice_id']

    cursor.execute("INSERT INTO payments VALUES (?, ?, ?, ?)",
                   (invoice_id, msg.chat.id, amount, "pending"))
    conn.commit()

    await msg.answer(
        f"💳 <b>Счёт создан</b>

"
        f"💰 Сумма: <b>${amount}</b>
"
        f"🔗 <a href='{pay_url}'>Оплатить</a>",
        parse_mode="HTML",
        disable_web_page_preview=True
    )

# START
@dp.message_handler(commands=['start'])
async def start(msg: types.Message):
    cursor.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (msg.from_user.id,))
    conn.commit()
    await msg.answer("🚀 Добро пожаловать", reply_markup=main_menu())

# ADMIN PANEL
@dp.message_handler(commands=['admin'])
async def admin(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("➕ Добавить номер", callback_data="add_num"))
    kb.add(InlineKeyboardButton("📋 Список номеров", callback_data="list_nums"))
    kb.add(InlineKeyboardButton("📊 Статистика", callback_data="stats"))

    await msg.answer("⚙️ Админ панель", reply_markup=kb)

# ADD NUMBER
@dp.callback_query_handler(lambda c: c.data == "add_num")
async def add_num(call: types.CallbackQuery):
    await AdminAdd.waiting.set()
    await call.message.answer("Введите: номер цена")

@dp.message_handler(state=AdminAdd.waiting)
async def save_num(msg: types.Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return

    try:
        number, price = msg.text.split()
        cursor.execute("INSERT INTO numbers (number, price) VALUES (?, ?)", (number, float(price)))
        conn.commit()
        await msg.answer("✅ Номер добавлен")
    except:
        await msg.answer("Ошибка")

    await state.finish()

# LIST NUMBERS
@dp.callback_query_handler(lambda c: c.data == "list_nums")
async def list_nums(call: types.CallbackQuery):
    cursor.execute("SELECT * FROM numbers")
    nums = cursor.fetchall()

    if not nums:
        return await call.message.edit_text("❌ Нет номеров")

    kb = InlineKeyboardMarkup()

    for n in nums:
        kb.add(InlineKeyboardButton(f"{n[1]} (${n[2]}) ❌", callback_data=f"del_{n[0]}"))
        kb.add(InlineKeyboardButton(f"✏️ Изменить {n[1]}", callback_data=f"edit_{n[0]}"))

    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="admin_back"))

    await call.message.edit_text("📋 Номера:", reply_markup=kb)

# DELETE NUMBER
@dp.callback_query_handler(lambda c: c.data.startswith("del_"))
async def delete_num(call: types.CallbackQuery):
    num_id = int(call.data.split("_")[1])
    cursor.execute("DELETE FROM numbers WHERE id=?", (num_id,))
    conn.commit()

    await call.answer("Удалено")
    await list_nums(call)

# EDIT NUMBER
@dp.callback_query_handler(lambda c: c.data.startswith("edit_"))
async def edit_num(call: types.CallbackQuery):
    num_id = int(call.data.split("_")[1])
    await AdminEdit.waiting.set()
    await call.message.answer(f"Введите новую цену для ID {num_id}")
    await call.answer()
    await call.message.answer(str(num_id))

@dp.message_handler(state=AdminEdit.waiting)
async def save_edit(msg: types.Message, state: FSMContext):
    try:
        parts = msg.text.split()
        if len(parts) != 2:
            return await msg.answer("Формат: id цена")

        num_id, price = parts
        cursor.execute("UPDATE numbers SET price=? WHERE id=?", (float(price), int(num_id)))
        conn.commit()

        await msg.answer("✅ Цена обновлена")
    except:
        await msg.answer("Ошибка")

    await state.finish()

# STATS
@dp.callback_query_handler(lambda c: c.data == "stats")
async def stats(call: types.CallbackQuery):
    cursor.execute("SELECT COUNT(*) FROM users")
    users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM rentals")
    rents = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(amount) FROM payments WHERE status='paid'")
    income = cursor.fetchone()[0] or 0

    await call.message.edit_text(f"📊 Статистика\n\n👥 Пользователи: {users}\n📱 Аренды: {rents}\n💰 Доход: ${income}")

@dp.callback_query_handler(lambda c: c.data == "admin_back")
async def admin_back(call: types.CallbackQuery):
    await admin(call.message)

# BACKGROUND TASKS
async def scheduler():
    while True:
        await asyncio.sleep(10)

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(scheduler())

    executor.start_polling(dp, skip_updates=True)
