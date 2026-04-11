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
ADMIN_ID = 8451049817

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

cursor.execute("""
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT,
    telegram_id INTEGER,
    service TEXT,
    link TEXT,
    quantity INTEGER
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

# ===== TELEGRAM =====
user_steps = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.message.chat_id
    user_id, balance = get_user(tg_id)

    keyboard = [
        ["👤 Account", "💰 Recharge"],
        ["📦 Orders", "🛒 Services"]
    ]

    await update.message.reply_text(
        f"✨ Welcome to Cherap SMM Service 🚀\n\n🆔 Your ID: {user_id}",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.message.chat_id
    text = update.message.text

    user_id, balance = get_user(tg_id)

    if text == "👤 Account":
        await update.message.reply_text(f"🆔 ID: {user_id}\n💰 Balance: ₹{balance}")

    elif text == "💰 Recharge":
        user_steps[tg_id] = "amount"
        await update.message.reply_text("Enter amount:")

    elif user_steps.get(tg_id) == "amount":
        if not text.isdigit():
            await update.message.reply_text("❌ Enter number")
            return

        amount = int(text)

        payment_link = client.payment_link.create({
            "amount": amount * 100,
            "currency": "INR",
            "notes": {"telegram_id": str(tg_id)}
        })

        await update.message.reply_text(f"💳 Pay here:\n{payment_link['short_url']}")
        user_steps[tg_id] = None

    elif text == "🛒 Services":
        await update.message.reply_text(
            "Select Service:",
            reply_markup=ReplyKeyboardMarkup(
                [["👍 Likes", "💬 Comments"]],
                resize_keyboard=True
            )
        )

    # ===== LIKES =====
    elif text == "👍 Likes":
        user_steps[tg_id] = "like_link"
        await update.message.reply_text(
            "🔥 Youtube Likes [No Drop] [Instant]\n💰 ₹25 / 1000\nMin 100\nSend Link:"
        )

    elif user_steps.get(tg_id) == "like_link":
        context.user_data["link"] = text
        user_steps[tg_id] = "like_qty"
        await update.message.reply_text("Enter Quantity:")

    elif user_steps.get(tg_id) == "like_qty":
        qty = int(text)

        if qty < 100:
            await update.message.reply_text("❌ Min 100")
            return

        price = (qty / 1000) * 25

        if balance < price:
            await update.message.reply_text(f"❌ Need ₹{price}")
            return

        cursor.execute("UPDATE users SET balance=balance-? WHERE telegram_id=?", (price, tg_id))
        conn.commit()

        res = requests.post(LIKE_API_URL, data={
            "key": LIKE_API_KEY,
            "action": "add",
            "service": LIKE_SERVICE_ID,
            "link": context.user_data["link"],
            "quantity": qty
        }).json()

        if "order" in res:
            cursor.execute("INSERT INTO orders VALUES (?, ?, ?, ?, ?)",
                           (res["order"], tg_id, "likes", context.user_data["link"], qty))
            conn.commit()
            await update.message.reply_text(f"✅ Order ID: {res['order']}")
        else:
            await update.message.reply_text("❌ Failed")

        user_steps[tg_id] = None

    # ===== COMMENTS =====
    elif text == "💬 Comments":
        user_steps[tg_id] = "c_link"
        await update.message.reply_text(
            "💬 Youtube Custom Comments (Instant)\n💰 ₹170 / 1000\nMin 10\nSend Link:"
        )

    elif user_steps.get(tg_id) == "c_link":
        context.user_data["link"] = text
        user_steps[tg_id] = "c_text"
        await update.message.reply_text("Send Comment Text:")

    elif user_steps.get(tg_id) == "c_text":
        context.user_data["comment"] = text
        user_steps[tg_id] = "c_qty"
        await update.message.reply_text("Enter Quantity:")

    elif user_steps.get(tg_id) == "c_qty":
        qty = int(text)

        if qty < 10:
            await update.message.reply_text("❌ Min 10")
            return

        price = (qty / 1000) * 170

        if balance < price:
            await update.message.reply_text(f"❌ Need ₹{price}")
            return

        cursor.execute("UPDATE users SET balance=balance-? WHERE telegram_id=?", (price, tg_id))
        conn.commit()

        res = requests.post(COMMENT_API_URL, data={
            "key": COMMENT_API_KEY,
            "action": "add",
            "service": COMMENT_SERVICE_ID,
            "link": context.user_data["link"],
            "comments": context.user_data["comment"],
            "quantity": qty
        }).json()

        if "order" in res:
            cursor.execute("INSERT INTO orders VALUES (?, ?, ?, ?, ?)",
                           (res["order"], tg_id, "comments", context.user_data["link"], qty))
            conn.commit()
            await update.message.reply_text(f"✅ Order ID: {res['order']}")
        else:
            await update.message.reply_text("❌ Failed")

        user_steps[tg_id] = None

    elif text == "📦 Orders":
        cursor.execute("SELECT * FROM orders WHERE telegram_id=?", (tg_id,))
        rows = cursor.fetchall()

        if not rows:
            await update.message.reply_text("No orders")
            return

        msg = "📦 Orders:\n"
        for r in rows[-5:]:
            msg += f"{r[2]} | {r[4]} | ID: {r[0]}\n"

        await update.message.reply_text(msg)

# ===== WEBHOOK (FINAL FIX) =====
app_web = Flask(__name__)

@app_web.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Razorpay-Signature")
    body = request.data

    expected = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, signature):
        return {"status": "invalid"}, 400

    data = request.json

    if data.get("event") == "payment_link.paid":
        payment_link = data["payload"]["payment_link"]["entity"]

        tg_id = int(payment_link["notes"]["telegram_id"])
        amount = payment_link["amount_paid"] / 100
        payment_id = payment_link["id"]

        cursor.execute("SELECT * FROM payments WHERE payment_id=?", (payment_id,))
        if cursor.fetchone():
            return {"status": "duplicate"}

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
