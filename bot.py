import requests
import razorpay
import sqlite3
import hmac
import hashlib
import os
import threading
import asyncio

from flask import Flask, request
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Bot
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

# ================= CONFIG =================
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

# ================= DB =================
conn = sqlite3.connect("smm.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
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

# ================= STATE =================
user_steps = {}

def menu():
    return ReplyKeyboardMarkup([
        ["👤 Account", "💰 Recharge"],
        ["📦 Orders", "🛒 Services"]
    ], resize_keyboard=True)

BACK = ReplyKeyboardMarkup([["⬅️ Back"]], resize_keyboard=True)

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.message.chat_id

    cursor.execute("INSERT OR IGNORE INTO users (telegram_id) VALUES (?)", (tg_id,))
    conn.commit()

    cursor.execute("SELECT balance FROM users WHERE telegram_id=?", (tg_id,))
    bal = cursor.fetchone()[0]

    await update.message.reply_text(
        f"✨ SMM BOT ACTIVE\n💰 Balance: ₹{bal}",
        reply_markup=menu()
    )

# ================= SERVICES =================
async def services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("👍 Likes ₹25/1000", callback_data="likes")],
        [InlineKeyboardButton("💬 Comments ₹250/1000", callback_data="comments")]
    ]

    await update.message.reply_text(
        "Select Service:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= CALLBACK =================
async def cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    tg_id = q.message.chat_id

    if q.data == "likes":
        user_steps[tg_id] = "like_link"
        await q.message.reply_text("Send Post Link:")

    elif q.data == "comments":
        user_steps[tg_id] = "c_link"
        await q.message.reply_text(
            "💬 Send comments (one per line)\nExample:\nNice video\n🔥🔥🔥\nGood job"
        )

# ================= MAIN HANDLER =================
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.message.chat_id
    text = update.message.text

    cursor.execute("SELECT balance FROM users WHERE telegram_id=?", (tg_id,))
    balance = cursor.fetchone()[0]

    step = user_steps.get(tg_id)

    # ================= ACCOUNT =================
    if text == "👤 Account":
        await update.message.reply_text(f"💰 Balance: ₹{balance}")

    # ================= RECHARGE =================
    elif text == "💰 Recharge":
        amount = int(text)

        payment = client.payment_link.create({
            "amount": amount * 100,
            "currency": "INR",
            "notes": {"telegram_id": str(tg_id)}
        })

        await update.message.reply_text(payment['short_url'])

    # ================= SERVICES =================
    elif text == "🛒 Services":
        await services(update, context)

    # ================= LIKE FLOW =================
    elif step == "like_link":
        context.user_data["link"] = text
        user_steps[tg_id] = "like_qty"
        await update.message.reply_text("Enter Likes Quantity:")

    elif step == "like_qty":
        qty = int(text)
        price = round((qty / 1000) * 25, 2)

        if balance < price:
            await update.message.reply_text("❌ Low Balance")
            return

        cursor.execute("UPDATE users SET balance=balance-? WHERE telegram_id=?",
                       (price, tg_id))
        conn.commit()

        res = requests.post(LIKE_API_URL, data={
            "key": LIKE_API_KEY,
            "action": "add",
            "service": LIKE_SERVICE_ID,
            "link": context.user_data["link"],
            "quantity": qty
        }).json()

        cursor.execute("INSERT INTO orders VALUES (?,?,?,?,?)",
                       (res.get("order", "NA"), tg_id, "likes",
                        context.user_data["link"], qty))
        conn.commit()

        await update.message.reply_text(
            f"✅ ORDER PLACED\n👍 Likes: {qty}\n💰 ₹{price}"
        )

        user_steps[tg_id] = None

    # ================= COMMENTS (FIXED FULL SYSTEM) =================
    elif step == "c_link":
        context.user_data["link"] = text
        user_steps[tg_id] = "c_text"
        await update.message.reply_text(
            "💬 Send comments (one per line)"
        )

    elif step == "c_text":
        comments = [c.strip() for c in text.split("\n") if c.strip()]
        qty = len(comments)

        if qty < 1:
            await update.message.reply_text("❌ No comments found")
            return

        price = round((qty / 1000) * 250, 2)

        context.user_data["comments"] = comments
        context.user_data["qty"] = qty
        context.user_data["price"] = price

        user_steps[tg_id] = "c_confirm"

        await update.message.reply_text(
            f"📦 ORDER SUMMARY\n\n"
            f"💬 Comments: {qty}\n"
            f"💰 Rate: ₹250 / 1000\n"
            f"💳 Total: ₹{price}\n\n"
            f"👉 Type YES to confirm / NO to cancel"
        )

    elif step == "c_confirm":
        if text.lower() == "no":
            user_steps[tg_id] = None
            await update.message.reply_text("❌ Cancelled")
            return

        if text.lower() != "yes":
            await update.message.reply_text("👉 YES or NO only")
            return

        qty = context.user_data["qty"]
        price = context.user_data["price"]
        comments = context.user_data["comments"]

        if balance < price:
            await update.message.reply_text("❌ Low Balance")
            return

        cursor.execute("UPDATE users SET balance=balance-? WHERE telegram_id=?",
                       (price, tg_id))
        conn.commit()

        res = requests.post(COMMENT_API_URL, data={
            "key": COMMENT_API_KEY,
            "action": "add",
            "service": COMMENT_SERVICE_ID,
            "link": context.user_data["link"],
            "comments": "\n".join(comments)
        }).json()

        cursor.execute("INSERT INTO orders VALUES (?,?,?,?,?)",
                       (res.get("order", "NA"), tg_id, "comments",
                        context.user_data["link"], qty))
        conn.commit()

        await update.message.reply_text(
            f"✅ ORDER PLACED\n💬 Comments: {qty}\n💰 ₹{price}\n📦 ID: {res.get('order')}"
        )

        user_steps[tg_id] = None

    # ================= ORDERS =================
    elif text == "📦 Orders":
        cursor.execute("SELECT * FROM orders WHERE telegram_id=?", (tg_id,))
        rows = cursor.fetchall()

        if not rows:
            await update.message.reply_text("No orders")
            return

        msg = "📦 LAST ORDERS\n\n"
        for r in rows[-5:]:
            msg += f"{r[2]} | {r[4]} | {r[0]}\n"

        await update.message.reply_text(msg)

# ================= RUN =================
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(cb))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

app.run_polling()
