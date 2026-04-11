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
ADMIN_ID = 1716557667

# ===== LIKE API (OLD) =====
LIKE_API_KEY = "7d01eb30166546130c171b26eecee191"
LIKE_API_URL = "https://tntsmm.in/api/v2"
LIKE_SERVICE_ID = "3062"

# ===== COMMENT API (NEW) =====
COMMENT_API_KEY = "a6a2e96cd415e968918b20baa261bc4b095f36c1"
COMMENT_API_URL = "https://smm-jupiter.com/api/v2"
COMMENT_SERVICE_ID = "13259"

# ===== RAZORPAY =====
RAZORPAY_KEY = "rzp_live_Sc7lXEOJ2ZWjPL"
RAZORPAY_SECRET = "KxRu3ssMBcNLTQ7LxMY0jZIQ"
WEBHOOK_SECRET = "ayush@123"

client = razorpay.Client(auth=(RAZORPAY_KEY, RAZORPAY_SECRET))
bot = Bot(token=BOT_TOKEN)

# ===== DATABASE (PERMANENT FIX) =====
if not os.path.exists("data"):
    os.makedirs("data")

conn = sqlite3.connect("data/users.db", check_same_thread=False)
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

# ===== USER =====
def get_user(tg_id):
    cursor.execute("SELECT id, balance FROM users WHERE telegram_id=?", (tg_id,))
    user = cursor.fetchone()

    if user:
        return user
    else:
        cursor.execute("INSERT INTO users (telegram_id) VALUES (?)", (tg_id,))
        conn.commit()
        return get_user(tg_id)

def update_balance(tg_id, amount):
    cursor.execute("UPDATE users SET balance = balance + ? WHERE telegram_id=?", (amount, tg_id))
    conn.commit()

# ===== MENU =====
def main_menu():
    return ReplyKeyboardMarkup([
        ["👤 Account", "💰 Recharge"],
        ["📦 Orders", "🛒 Services"],
        ["🔙 Back"]
    ], resize_keyboard=True)

# ===== TELEGRAM =====
user_steps = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.message.chat_id
    user_id, _ = get_user(tg_id)

    await update.message.reply_text(
        f"✨ Welcome to Cherap SMM Service 🚀\n🆔 Your ID: {user_id}",
        reply_markup=main_menu()
    )

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.message.chat_id
    text = update.message.text

    user_id, balance = get_user(tg_id)

    # ===== BACK =====
    if text == "🔙 Back":
        user_steps[tg_id] = None
        await update.message.reply_text("🔙 Back to menu", reply_markup=main_menu())

    # ===== ACCOUNT =====
    elif text == "👤 Account":
        await update.message.reply_text(f"🆔 ID: {user_id}\n💰 Balance: ₹{balance}")

    # ===== RECHARGE =====
    elif text == "💰 Recharge":
        user_steps[tg_id] = "amount"
        await update.message.reply_text("Enter amount:")

    elif user_steps.get(tg_id) == "amount":
        if not text.isdigit():
            return await update.message.reply_text("❌ Enter number")

        amount = int(text)

        payment_link = client.payment_link.create({
            "amount": amount * 100,
            "currency": "INR",
            "notes": {"telegram_id": str(tg_id)}
        })

        await update.message.reply_text(f"💳 Pay here:\n{payment_link['short_url']}")
        user_steps[tg_id] = None

    # ===== SERVICES =====
    elif text == "🛒 Services":
        await update.message.reply_text(
            "Select Service:",
            reply_markup=ReplyKeyboardMarkup(
                [["👍 Likes", "💬 Comments"], ["🔙 Back"]],
                resize_keyboard=True
            )
        )

    # ===== LIKES =====
    elif text == "👍 Likes":
        user_steps[tg_id] = "like_link"
        await update.message.reply_text("🔥 Likes ₹29/1000\nMin 100\nSend Link:")

    elif user_steps.get(tg_id) == "like_link":
        context.user_data["link"] = text
        user_steps[tg_id] = "like_qty"
        await update.message.reply_text("Enter Quantity:")

    elif user_steps.get(tg_id) == "like_qty":
        qty = int(text)
        price = (qty / 1000) * 29

        if balance < price:
            return await update.message.reply_text("❌ Low balance")

        update_balance(tg_id, -price)

        res = requests.post(LIKE_API_URL, data={
            "key": LIKE_API_KEY,
            "action": "add",
            "service": LIKE_SERVICE_ID,
            "link": context.user_data["link"],
            "quantity": qty
        }).json()

        await update.message.reply_text(f"✅ Order: {res}")

        user_steps[tg_id] = None

    # ===== COMMENTS =====
    elif text == "💬 Comments":
        user_steps[tg_id] = "c_link"
        await update.message.reply_text("💬 Comments ₹250/1000\nMin 10\nSend Link:")

    elif user_steps.get(tg_id) == "c_link":
        context.user_data["link"] = text
        user_steps[tg_id] = "c_text"
        await update.message.reply_text("Send comment text:")

    elif user_steps.get(tg_id) == "c_text":
        context.user_data["comment"] = text
        user_steps[tg_id] = "c_qty"
        await update.message.reply_text("Enter quantity:")

    elif user_steps.get(tg_id) == "c_qty":
        qty = int(text)
        price = (qty / 1000) * 250

        if balance < price:
            return await update.message.reply_text("❌ Low balance")

        update_balance(tg_id, -price)

        res = requests.post(COMMENT_API_URL, data={
            "key": COMMENT_API_KEY,
            "action": "add",
            "service": COMMENT_SERVICE_ID,
            "link": context.user_data["link"],
            "comments": context.user_data["comment"],
            "quantity": qty
        }).json()

        await update.message.reply_text(f"✅ Order: {res}")

        user_steps[tg_id] = None

    # ===== ADMIN =====
    elif text == "/admin":
        if tg_id != 1716557667:
            return

        await update.message.reply_text(
            "👑 Admin Panel",
            reply_markup=ReplyKeyboardMarkup(
                [["👥 Users", "💰 Total Balance"], ["🔙 Back"]],
                resize_keyboard=True
            )
        )

    elif text == "👥 Users" and tg_id == ADMIN_ID:
        cursor.execute("SELECT COUNT(*) FROM users")
        total = cursor.fetchone()[0]
        await update.message.reply_text(f"👥 Users: {total}")

    elif text == "💰 Total Balance" and tg_id == ADMIN_ID:
        cursor.execute("SELECT SUM(balance) FROM users")
        total = cursor.fetchone()[0] or 0
        await update.message.reply_text(f"💰 Total: ₹{total}")

# ===== WEBHOOK FIX =====
app_web = Flask(__name__)

@app_web.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    if data.get("event") == "payment_link.paid":
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

        asyncio.run(bot.send_message(chat_id=tg_id, text=f"✅ ₹{amount} added"))

    return {"status": "ok"}

# ===== RUN =====
def start_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.run_polling(drop_pending_updates=True)

def start_web():
    port = int(os.environ.get("PORT", 5000))
    app_web.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=start_web).start()
    start_bot()
