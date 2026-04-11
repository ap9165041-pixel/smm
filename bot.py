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

# ===== DYNAMIC PRICING =====
LIKE_PRICE = 25       # per 1000
COMMENT_PRICE = 250   # per 1000

client = razorpay.Client(auth=(RAZORPAY_KEY, RAZORPAY_SECRET))
bot = Bot(token=BOT_TOKEN)

# ===== DATABASE =====
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE,
    balance REAL DEFAULT 0
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS payments (
    payment_id TEXT PRIMARY KEY,
    telegram_id INTEGER,
    amount REAL
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT,
    telegram_id INTEGER,
    service TEXT,
    link TEXT,
    quantity INTEGER
)""")

conn.commit()

# ===== STATES =====
user_steps = {}

# ===== KEYBOARDS =====
def main_menu():
    return ReplyKeyboardMarkup(
        [
            ["👤 Account", "💰 Recharge"],
            ["📦 Orders", "🛒 Services"]
        ],
        resize_keyboard=True
    )

def services_menu():
    return ReplyKeyboardMarkup(
        [
            [f"👍 Likes (₹{LIKE_PRICE}/1000)", f"💬 Comments (₹{COMMENT_PRICE}/1000)"],
            ["⬅️ Back"]
        ],
        resize_keyboard=True
    )

def confirm_kb():
    return ReplyKeyboardMarkup(
        [["✅ Confirm", "❌ Cancel"]],
        resize_keyboard=True
    )

BACK_KB = ReplyKeyboardMarkup([["⬅️ Back"]], resize_keyboard=True)

# ===== USER =====
def get_user(tg_id):
    cursor.execute("SELECT id, balance FROM users WHERE telegram_id=?", (tg_id,))
    user = cursor.fetchone()

    if not user:
        cursor.execute("INSERT INTO users (telegram_id) VALUES (?)", (tg_id,))
        conn.commit()
        return get_user(tg_id)

    return user

def update_balance(tg_id, amount):
    cursor.execute("UPDATE users SET balance = balance + ? WHERE telegram_id=?", (amount, tg_id))
    conn.commit()

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.message.chat_id
    user_id, balance = get_user(tg_id)

    await update.message.reply_text(
        f"✨ Welcome SMM Bot 🚀\n🆔 ID: {user_id}\n💰 Balance: ₹{balance}",
        reply_markup=main_menu()
    )

# ===== MAIN HANDLER =====
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global LIKE_PRICE, COMMENT_PRICE

    tg_id = update.message.chat_id
    text = update.message.text

    user_id, balance = get_user(tg_id)
    step = user_steps.get(tg_id)

    # BACK
    if text == "⬅️ Back":
        user_steps[tg_id] = None
        await update.message.reply_text("🔙 Main Menu", reply_markup=main_menu())
        return

    # ACCOUNT
    if text == "👤 Account":
        await update.message.reply_text(f"🆔 ID: {user_id}\n💰 Balance: ₹{balance}")

    # ===== ADMIN PANEL =====
    elif tg_id == ADMIN_ID and text == "/admin":
        await update.message.reply_text(
            "👑 Admin Panel\n\n"
            "/setlike 30\n"
            "/setcomment 300\n"
            "/apibal"
        )

    elif tg_id == ADMIN_ID and text.startswith("/setlike"):
        LIKE_PRICE = int(text.split()[1])
        await update.message.reply_text(f"✅ Like price updated: ₹{LIKE_PRICE}/1000")

    elif tg_id == ADMIN_ID and text.startswith("/setcomment"):
        COMMENT_PRICE = int(text.split()[1])
        await update.message.reply_text(f"✅ Comment price updated: ₹{COMMENT_PRICE}/1000")

    elif tg_id == ADMIN_ID and text == "/apibal":
        like_bal = requests.post(LIKE_API_URL, data={"key": LIKE_API_KEY, "action": "balance"}).json()
        comment_bal = requests.post(COMMENT_API_URL, data={"key": COMMENT_API_KEY, "action": "balance"}).json()

        await update.message.reply_text(f"LIKE API: {like_bal}\nCOMMENT API: {comment_bal}")

    # ===== RECHARGE =====
    elif text == "💰 Recharge":
        user_steps[tg_id] = "amount"
        await update.message.reply_text("Enter amount:", reply_markup=BACK_KB)

    elif step == "amount":
        if not text.isdigit():
            await update.message.reply_text("❌ Enter number")
            return

        amount = int(text)

        payment = client.payment_link.create({
            "amount": amount * 100,
            "currency": "INR",
            "notes": {"telegram_id": str(tg_id)}
        })

        await update.message.reply_text(payment['short_url'])
        user_steps[tg_id] = None

    # SERVICES
    elif text == "🛒 Services":
        await update.message.reply_text("Choose Service:", reply_markup=services_menu())

    # ===== LIKES =====
    elif "👍 Likes" in text:
        user_steps[tg_id] = "like_link"
        await update.message.reply_text("🔗 Send Link:", reply_markup=BACK_KB)

    elif step == "like_link":
        context.user_data["link"] = text
        user_steps[tg_id] = "like_qty"
        await update.message.reply_text("Enter Quantity:")

    elif step == "like_qty":
        qty = int(text)
        price = (qty / 1000) * LIKE_PRICE

        context.user_data["qty"] = qty
        context.user_data["price"] = price

        await update.message.reply_text(
            f"Likes: {qty}\nPrice: ₹{price}\nConfirm?",
            reply_markup=confirm_kb()
        )
        user_steps[tg_id] = "like_confirm"

    elif step == "like_confirm":
        if text == "❌ Cancel":
            user_steps[tg_id] = None
            await update.message.reply_text("Cancelled", reply_markup=main_menu())
            return

        qty = context.user_data["qty"]
        price = context.user_data["price"]

        if balance < price:
            await update.message.reply_text("❌ Low balance")
            return

        res = requests.post(LIKE_API_URL, data={
            "key": LIKE_API_KEY,
            "action": "add",
            "service": LIKE_SERVICE_ID,
            "link": context.user_data["link"],
            "quantity": qty
        }).json()

        if "order" in res:
            update_balance(tg_id, -price)
            await update.message.reply_text(f"✅ Order: {res['order']}", reply_markup=main_menu())
        else:
            await update.message.reply_text(f"❌ Failed\n{res}", reply_markup=main_menu())

        user_steps[tg_id] = None

    # ===== COMMENTS =====
    elif "💬 Comments" in text:
        user_steps[tg_id] = "c_link"
        await update.message.reply_text("🔗 Send Link:", reply_markup=BACK_KB)

    elif step == "c_link":
        context.user_data["link"] = text
        user_steps[tg_id] = "c_text"
        await update.message.reply_text("Send comments (each line new):")

    elif step == "c_text":
        comments = text.split("\n")
        qty = len([c for c in comments if c.strip() != ""])

        price = (qty / 1000) * COMMENT_PRICE

        context.user_data["comments"] = text
        context.user_data["qty"] = qty
        context.user_data["price"] = price

        await update.message.reply_text(
            f"Comments: {qty}\nPrice: ₹{price}\nConfirm?",
            reply_markup=confirm_kb()
        )
        user_steps[tg_id] = "c_confirm"

    elif step == "c_confirm":
        if text == "❌ Cancel":
            user_steps[tg_id] = None
            await update.message.reply_text("Cancelled", reply_markup=main_menu())
            return

        qty = context.user_data["qty"]
        price = context.user_data["price"]

        if balance < price:
            await update.message.reply_text("❌ Low balance")
            return

        res = requests.post(COMMENT_API_URL, data={
            "key": COMMENT_API_KEY,
            "action": "add",
            "service": COMMENT_SERVICE_ID,
            "link": context.user_data["link"],
            "comments": context.user_data["comments"]
        }).json()

        if "order" in res:
            update_balance(tg_id, -price)
            await update.message.reply_text(f"✅ Order: {res['order']}", reply_markup=main_menu())
        else:
            await update.message.reply_text(f"❌ Failed\n{res}", reply_markup=main_menu())

        user_steps[tg_id] = None

# ===== WEBHOOK =====
app_web = Flask(__name__)

@app_web.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    if data.get("event") == "payment_link.paid":
        entity = data["payload"]["payment_link"]["entity"]

        tg_id = int(entity["notes"]["telegram_id"])
        amount = entity["amount_paid"] / 100

        update_balance(tg_id, amount)
        asyncio.run(bot.send_message(chat_id=tg_id, text=f"₹{amount} added"))

    return {"status": "ok"}

# ===== RUN =====
def start_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.run_polling()

def start_web():
    app_web.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    threading.Thread(target=start_web).start()
    start_bot()
