import requests
import razorpay
import sqlite3
import hmac
import hashlib
import os
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import threading
import asyncio

# ===== CONFIG =====
BOT_TOKEN = "8748370733:AAHmioo1yYD4GcozjnJVVsN8niakHDzmcnE"
API_KEY = "7d01eb30166546130c171b26eecee191"
API_URL = "https://tntsmm.in/api/v2"

RAZORPAY_KEY = "rzp_live_Sc7lXEOJ2ZWjPL"
RAZORPAY_SECRET = "KxRu3ssMBcNLTQ7LxMY0jZIQ"
WEBHOOK_SECRET = "ayush@123"
ADMIN_ID = 8451049817  # 👈 apna telegram id

client = razorpay.Client(auth=(RAZORPAY_KEY, RAZORPAY_SECRET))
bot = Bot(token=BOT_TOKEN)

# ===== DATABASE =====
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE,
    balance REAL DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS payments (
    payment_id TEXT PRIMARY KEY,
    telegram_id INTEGER,
    amount REAL
)
""")
conn.commit()

# ===== USER SYSTEM =====
def get_or_create_user(tg_id):
    cursor.execute("SELECT id, balance FROM users WHERE telegram_id=?", (tg_id,))
    user = cursor.fetchone()

    if user:
        return user
    else:
        cursor.execute("INSERT INTO users (telegram_id) VALUES (?)", (tg_id,))
        conn.commit()
        return get_or_create_user(tg_id)

def update_balance(tg_id, amount):
    cursor.execute("UPDATE users SET balance = balance + ? WHERE telegram_id=?", (amount, tg_id))
    conn.commit()

# ===== TELEGRAM =====
user_steps = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.message.chat_id
    user_id, balance = get_or_create_user(tg_id)

    keyboard = [
        ["💰 Balance", "🔄 Recharge"],
        ["🆔 My ID"],
        ["🛠 Admin Panel"]
    ]

    await update.message.reply_text(
        f"🚀 Welcome\nYour ID: {user_id}",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.message.chat_id
    text = update.message.text

    user_id, balance = get_or_create_user(tg_id)

    # ===== USER =====
    if text == "💰 Balance":
        await update.message.reply_text(f"💰 Balance: ₹{balance}")

    elif text == "🆔 My ID":
        await update.message.reply_text(f"🆔 Your ID: {user_id}")

    elif text == "🔄 Recharge":
        user_steps[tg_id] = "amount"
        await update.message.reply_text("Enter amount:")

    elif user_steps.get(tg_id) == "amount":
        amount = int(text)

        payment_link = client.payment_link.create({
            "amount": amount * 100,
            "currency": "INR",
            "notes": {"telegram_id": str(tg_id)}
        })

        await update.message.reply_text(payment_link["short_url"])
        user_steps[tg_id] = None

    # ===== ADMIN =====
    elif text == "🛠 Admin Panel":
        if tg_id != ADMIN_ID:
            await update.message.reply_text("❌ Access Denied")
            return

        await update.message.reply_text(
            "Admin Panel",
            reply_markup=ReplyKeyboardMarkup(
                [["👥 Total Users", "➕ Add Balance"]],
                resize_keyboard=True
            )
        )

    elif text == "👥 Total Users" and tg_id == ADMIN_ID:
        cursor.execute("SELECT COUNT(*) FROM users")
        total = cursor.fetchone()[0]
        await update.message.reply_text(f"Users: {total}")

    elif text == "➕ Add Balance" and tg_id == ADMIN_ID:
        user_steps[tg_id] = "admin_user"
        await update.message.reply_text("Enter User ID:")

    elif user_steps.get(tg_id) == "admin_user":
        context.user_data["target"] = int(text)
        user_steps[tg_id] = "admin_amount"
        await update.message.reply_text("Enter amount:")

    elif user_steps.get(tg_id) == "admin_amount":
        amount = float(text)
        uid = context.user_data["target"]

        cursor.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amount, uid))
        conn.commit()

        await update.message.reply_text("Balance Added")
        user_steps[tg_id] = None

# ===== WEBHOOK =====
app_web = Flask(__name__)

@app_web.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Razorpay-Signature")
    body = request.data

    expected = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, signature):
        return {"status": "invalid"}, 400

    data = request.json

    if data.get("event") == "payment.captured":
        payment = data["payload"]["payment"]["entity"]
        payment_id = payment["id"]

        cursor.execute("SELECT * FROM payments WHERE payment_id=?", (payment_id,))
        if cursor.fetchone():
            return {"status": "duplicate"}

        tg_id = int(payment["notes"]["telegram_id"])
        amount = payment["amount"] / 100

        update_balance(tg_id, amount)

        cursor.execute("INSERT INTO payments VALUES (?, ?, ?)", (payment_id, tg_id, amount))
        conn.commit()

        asyncio.run(bot.send_message(chat_id=tg_id, text=f"₹{amount} added"))

    return {"status": "ok"}

# ===== RUN =====
def start_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.run_polling()

def start_web():
    port = int(os.environ.get("PORT", 5000))
    app_web.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=start_web).start()
    start_bot()
