```python
import requests
import razorpay
import sqlite3
import hmac
import hashlib
import os
import threading
import asyncio
import time

from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

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

cursor.execute("""CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER UNIQUE,
    balance REAL DEFAULT 0
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT,
    telegram_id INTEGER,
    service TEXT,
    link TEXT,
    quantity INTEGER
)""")

conn.commit()

# ===== STATE =====
user_steps = {}
ADMIN_MODE = {}

PRICES = {
    "likes": 25,
    "comments": 250
}

# ===== KEYBOARD =====
def main_menu():
    return ReplyKeyboardMarkup([
        ["👤 Account", "💰 Recharge"],
        ["📦 Orders", "🛒 Services"]
    ], resize_keyboard=True)

def services_menu():
    return ReplyKeyboardMarkup([
        [f"👍 Likes (₹{PRICES['likes']}/1000)", f"💬 Comments (₹{PRICES['comments']}/1000)"],
        ["⬅️ Back"]
    ], resize_keyboard=True)

def confirm_kb():
    return ReplyKeyboardMarkup([["✅ Confirm", "❌ Cancel"]], resize_keyboard=True)

BACK = ReplyKeyboardMarkup([["⬅️ Back"]], resize_keyboard=True)

# ===== USER =====
def get_user(tg_id):
    cursor.execute("SELECT balance FROM users WHERE telegram_id=?", (tg_id,))
    user = cursor.fetchone()

    if not user:
        cursor.execute("INSERT INTO users VALUES (?, ?)", (tg_id, 0))
        conn.commit()
        return 0

    return user[0]

def update_balance(tg_id, amount):
    cursor.execute("UPDATE users SET balance = balance + ? WHERE telegram_id=?", (amount, tg_id))
    conn.commit()

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bal = get_user(update.message.chat_id)
    await update.message.reply_text(f"💰 Balance: ₹{bal}", reply_markup=main_menu())

# ===== ADMIN =====
async def admin_panel(update):
    kb = ReplyKeyboardMarkup([
        ["📊 API Balance", "💲 Edit Price"],
        ["⬅️ Back"]
    ], resize_keyboard=True)
    await update.message.reply_text("👨‍💼 Admin Panel", reply_markup=kb)

# ===== MAIN =====
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.message.chat_id
    text = update.message.text
    bal = get_user(tg_id)
    step = user_steps.get(tg_id)

    # BACK
    if text == "⬅️ Back":
        user_steps[tg_id] = None
        ADMIN_MODE[tg_id] = None
        await update.message.reply_text("🏠 Main Menu", reply_markup=main_menu())
        return

    # ADMIN
    if tg_id == ADMIN_ID:
        if text == "/admin":
            await admin_panel(update)
            return

        if text == "📊 API Balance":
            like = requests.post(LIKE_API_URL, data={"key": LIKE_API_KEY, "action": "balance"}).json()
            comment = requests.post(COMMENT_API_URL, data={"key": COMMENT_API_KEY, "action": "balance"}).json()
            await update.message.reply_text(f"👍 {like}\n💬 {comment}")
            return

        if text == "💲 Edit Price":
            ADMIN_MODE[tg_id] = "service"
            await update.message.reply_text("likes / comments?")
            return

        if ADMIN_MODE.get(tg_id) == "service":
            context.user_data["srv"] = text
            ADMIN_MODE[tg_id] = "price"
            await update.message.reply_text("Enter new price:")
            return

        if ADMIN_MODE.get(tg_id) == "price":
            PRICES[context.user_data["srv"]] = int(text)
            ADMIN_MODE[tg_id] = None
            await update.message.reply_text("✅ Updated", reply_markup=main_menu())
            return

    # ACCOUNT
    if text == "👤 Account":
        await update.message.reply_text(f"💰 Balance: ₹{bal}")

    # RECHARGE
    elif text == "💰 Recharge":
        user_steps[tg_id] = "amount"
        await update.message.reply_text("Enter amount:", reply_markup=BACK)

    elif step == "amount":
        amt = int(text)
        link = client.payment_link.create({
            "amount": amt * 100,
            "currency": "INR",
            "notes": {"telegram_id": str(tg_id)}
        })
        await update.message.reply_text(link['short_url'], reply_markup=main_menu())
        user_steps[tg_id] = None

    # SERVICES
    elif text == "🛒 Services":
        await update.message.reply_text("Choose:", reply_markup=services_menu())

    # LIKE FLOW
    elif "Likes" in text:
        user_steps[tg_id] = "like_link"
        await update.message.reply_text("Send link:", reply_markup=BACK)

    elif step == "like_link":
        context.user_data["link"] = text
        user_steps[tg_id] = "like_qty"
        await update.message.reply_text("Quantity:")

    elif step == "like_qty":
        qty = int(text)
        price = (qty / 1000) * PRICES["likes"]

        context.user_data["qty"] = qty
        context.user_data["price"] = price

        await update.message.reply_text(f"₹{price} Confirm?", reply_markup=confirm_kb())
        user_steps[tg_id] = "like_confirm"

    elif step == "like_confirm":
        if text == "❌ Cancel":
            await update.message.reply_text("Cancelled", reply_markup=main_menu())
            user_steps[tg_id] = None
            return

        if bal < context.user_data["price"]:
            await update.message.reply_text("Low balance", reply_markup=main_menu())
            return

        res = requests.post(LIKE_API_URL, data={
            "key": LIKE_API_KEY,
            "action": "add",
            "service": LIKE_SERVICE_ID,
            "link": context.user_data["link"],
            "quantity": context.user_data["qty"]
        }).json()

        if "order" in res:
            update_balance(tg_id, -context.user_data["price"])
            await update.message.reply_text("✅ Done", reply_markup=main_menu())
        else:
            await update.message.reply_text("❌ Failed", reply_markup=main_menu())

        user_steps[tg_id] = None

    # COMMENT FLOW
    elif "Comments" in text:
        user_steps[tg_id] = "c_link"
        await update.message.reply_text("Send link:", reply_markup=BACK)

    elif step == "c_link":
        context.user_data["link"] = text
        user_steps[tg_id] = "c_text"
        await update.message.reply_text("Send comments (line by line):")

    elif step == "c_text":
        comments = text.split("\n")
        qty = len(comments)
        price = (qty / 1000) * PRICES["comments"]

        context.user_data["comments"] = text
        context.user_data["price"] = price

        await update.message.reply_text(f"₹{price} Confirm?", reply_markup=confirm_kb())
        user_steps[tg_id] = "c_confirm"

    elif step == "c_confirm":
        if text == "❌ Cancel":
            await update.message.reply_text("Cancelled", reply_markup=main_menu())
            user_steps[tg_id] = None
            return

        if bal < context.user_data["price"]:
            await update.message.reply_text("Low balance", reply_markup=main_menu())
            return

        res = requests.post(COMMENT_API_URL, data={
            "key": COMMENT_API_KEY,
            "action": "add",
            "service": COMMENT_SERVICE_ID,
            "link": context.user_data["link"],
            "comments": context.user_data["comments"]
        }).json()

        if "order" in res:
            update_balance(tg_id, -context.user_data["price"])
            await update.message.reply_text("✅ Done", reply_markup=main_menu())
        else:
            await update.message.reply_text("❌ Failed", reply_markup=main_menu())

        user_steps[tg_id] = None

    # ORDERS
    elif text == "📦 Orders":
        cursor.execute("SELECT * FROM orders WHERE telegram_id=?", (tg_id,))
        rows = cursor.fetchall()
        msg = "\n".join([str(r) for r in rows[-5:]]) or "No orders"
        await update.message.reply_text(msg)

# ===== WEBHOOK =====
app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if data.get("event") == "payment_link.paid":
        tg_id = int(data["payload"]["payment_link"]["entity"]["notes"]["telegram_id"])
        amt = data["payload"]["payment_link"]["entity"]["amount_paid"] / 100
        update_balance(tg_id, amt)
        asyncio.run(bot.send_message(tg_id, f"₹{amt} added"))
    return {"ok": True}

# ===== API BALANCE CHECK =====
def checker():
    while True:
        try:
            like = requests.post(LIKE_API_URL, data={"key": LIKE_API_KEY, "action": "balance"}).json()
            if float(like.get("balance", 0)) < 10:
                bot.send_message(ADMIN_ID, "⚠️ Likes API LOW")
        except:
            pass
        time.sleep(300)

# ===== RUN =====
def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT, handle))
    app.run_polling()

def run_web():
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    threading.Thread(target=checker).start()
    run_bot()
```
