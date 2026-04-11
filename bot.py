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


client = razorpay.Client(auth=(RAZORPAY_KEY, RAZORPAY_SECRET))
bot = Bot(token=BOT_TOKEN)

# ===== DATABASE =====
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance REAL DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS payments (
    payment_id TEXT PRIMARY KEY,
    user_id INTEGER,
    amount REAL
)
""")
conn.commit()

# ===== FUNCTIONS =====
def get_user(uid):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    user = cursor.fetchone()

    if not user:
        cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)", (uid, 0))
        conn.commit()
        return (uid, 0)

    return user

def update_balance(uid, amount):
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, uid))
    conn.commit()

# ===== TELEGRAM =====
user_steps = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.chat_id
    get_user(uid)

    keyboard = [["💰 Balance", "🔄 Recharge"], ["👍 YouTube Likes"]]

    await update.message.reply_text(
        "🚀 Welcome to SMM Bot",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.chat_id
    text = update.message.text

    user = get_user(uid)
    balance = user[1]

    if text == "💰 Balance":
        await update.message.reply_text(f"💰 Balance: ₹{balance}")

    elif text == "🔄 Recharge":
        user_steps[uid] = "amount"
        await update.message.reply_text("💰 Enter amount:")

    elif user_steps.get(uid) == "amount":
        if not text.isdigit():
            await update.message.reply_text("❌ Enter valid number")
            return

        amount = int(text)

        payment_link = client.payment_link.create({
            "amount": amount * 100,
            "currency": "INR",
            "description": "Wallet Recharge",
            "notes": {"user_id": str(uid)}
        })

        await update.message.reply_text(f"💳 Pay here:\n{payment_link['short_url']}")
        user_steps[uid] = None

    elif text == "👍 YouTube Likes":
        user_steps[uid] = "yt_link"
        await update.message.reply_text("🔗 Send YouTube link")

    elif user_steps.get(uid) == "yt_link":
        context.user_data["link"] = text
        user_steps[uid] = "yt_qty"
        await update.message.reply_text("📊 Enter quantity (1000 = ₹20)")

    elif user_steps.get(uid) == "yt_qty":
        if not text.isdigit():
            await update.message.reply_text("❌ Invalid quantity")
            return

        qty = int(text)
        price = (qty / 1000) * 20

        if balance < price:
            await update.message.reply_text(f"❌ Need ₹{price}")
            return

        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (price, uid))
        conn.commit()

        data = {
            "key": API_KEY,
            "action": "add",
            "service": "3062",
            "link": context.user_data["link"],
            "quantity": qty
        }

        res = requests.post(API_URL, data=data).json()

        if "order" in res:
            await update.message.reply_text(f"✅ Order Done\n🆔 {res['order']}")
        else:
            await update.message.reply_text("❌ Order failed")

        user_steps[uid] = None

# ===== WEBHOOK =====
app_web = Flask(__name__)

@app_web.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Razorpay-Signature")
    body = request.data

    expected = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, signature):
        return {"status": "invalid signature"}, 400

    data = request.json

    if data.get("event") == "payment.captured":
        payment = data["payload"]["payment"]["entity"]
        payment_id = payment["id"]

        # duplicate check
        cursor.execute("SELECT * FROM payments WHERE payment_id=?", (payment_id,))
        if cursor.fetchone():
            return {"status": "duplicate"}

        uid = int(payment["notes"]["user_id"])
        amount = payment["amount"] / 100

        update_balance(uid, amount)

        cursor.execute("INSERT INTO payments VALUES (?, ?, ?)", (payment_id, uid, amount))
        conn.commit()

        asyncio.run(bot.send_message(chat_id=uid, text=f"✅ ₹{amount} added"))

    return {"status": "ok"}

# ===== RUN =====
def start_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    print("Bot Running...")
    app.run_polling()

def start_web():
    port = int(os.environ.get("PORT", 5000))
    app_web.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=start_web).start()
    start_bot()
