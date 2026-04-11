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

cursor.execute("""CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
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

cursor.execute("""CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)""")

# default prices
def set_defaults():
    defaults = {"like_price": "25", "comment_price": "250"}
    for k, v in defaults.items():
        cursor.execute("INSERT OR IGNORE INTO settings VALUES (?, ?)", (k, v))
    conn.commit()

set_defaults()

def get_setting(key):
    cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
    r = cursor.fetchone()
    return float(r[0]) if r else 0

conn.commit()

# ===== STATES =====
user_steps = {}

# ===== KEYBOARDS =====
def main_menu():
    return ReplyKeyboardMarkup(
        [["👤 Account", "💰 Recharge"],
         ["📦 Orders", "🛒 Services"]],
        resize_keyboard=True
    )

def services_menu():
    return ReplyKeyboardMarkup(
        [["👍 Likes", "💬 Comments"],
         ["⬅️ Back"]],
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
    cursor.execute("SELECT balance FROM users WHERE telegram_id=?", (tg_id,))
    user = cursor.fetchone()

    if not user:
        cursor.execute("INSERT INTO users VALUES (?, 0)", (tg_id,))
        conn.commit()
        return 0

    return user[0]

def update_balance(tg_id, amount):
    cursor.execute("UPDATE users SET balance = balance + ? WHERE telegram_id=?", (amount, tg_id))
    conn.commit()

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.message.chat_id
    balance = get_user(tg_id)

    await update.message.reply_text(
        f"✨ Welcome\n💰 Balance: ₹{balance}",
        reply_markup=main_menu()
    )

# ===== MAIN =====
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.message.chat_id
    text = update.message.text
    balance = get_user(tg_id)
    step = user_steps.get(tg_id)

    if text == "⬅️ Back":
        user_steps[tg_id] = None
        await update.message.reply_text("Main Menu", reply_markup=main_menu())
        return

    if text == "👤 Account":
        await update.message.reply_text(f"💰 Balance: ₹{balance}")

    elif text == "💰 Recharge":
        user_steps[tg_id] = "amount"
        await update.message.reply_text("Enter amount:", reply_markup=BACK_KB)

    elif step == "amount":
        if not text.isdigit():
            return await update.message.reply_text("Enter valid number")

        amount = int(text)

        payment = client.payment_link.create({
            "amount": amount * 100,
            "currency": "INR",
            "notes": {"telegram_id": str(tg_id)}
        })

        await update.message.reply_text(payment['short_url'])
        user_steps[tg_id] = None

    elif text == "🛒 Services":
        await update.message.reply_text("Choose Service:", reply_markup=services_menu())

    # ===== LIKE =====
    elif text == "👍 Likes":
        user_steps[tg_id] = "like_link"
        await update.message.reply_text("Send link:", reply_markup=BACK_KB)

    elif step == "like_link":
        context.user_data["link"] = text
        user_steps[tg_id] = "like_qty"
        await update.message.reply_text("Enter quantity:")

    elif step == "like_qty":
        if not text.isdigit():
            return await update.message.reply_text("Invalid")

        qty = int(text)
        price = (qty / 1000) * get_setting("like_price")

        context.user_data["qty"] = qty
        context.user_data["price"] = price

        await update.message.reply_text(
            f"Qty: {qty}\nPrice: ₹{price}\nConfirm?",
            reply_markup=confirm_kb()
        )

        user_steps[tg_id] = "like_confirm"

    elif step == "like_confirm":
        if text == "❌ Cancel":
            user_steps[tg_id] = None
            return await update.message.reply_text("Cancelled", reply_markup=main_menu())

        qty = context.user_data["qty"]
        price = context.user_data["price"]

        if balance < price:
            return await update.message.reply_text("Low balance")

        res = requests.post(LIKE_API_URL, data={
            "key": LIKE_API_KEY,
            "action": "add",
            "service": LIKE_SERVICE_ID,
            "link": context.user_data["link"],
            "quantity": qty
        }).json()

        if "order" in res:
            update_balance(tg_id, -price)

            cursor.execute("INSERT INTO orders VALUES (?, ?, ?, ?, ?)",
                           (res["order"], tg_id, "likes", context.user_data["link"], qty))
            conn.commit()

            await update.message.reply_text(
                f"✅ Order Placed\nID: {res['order']}",
                reply_markup=main_menu()
            )
        else:
            await bot.send_message(ADMIN_ID, f"LIKE ERROR: {res}")
            await update.message.reply_text("Order Failed", reply_markup=main_menu())

        user_steps[tg_id] = None

    # ===== COMMENTS =====
    elif text == "💬 Comments":
        user_steps[tg_id] = "c_link"
        await update.message.reply_text("Send link:", reply_markup=BACK_KB)

    elif step == "c_link":
        context.user_data["link"] = text
        user_steps[tg_id] = "c_text"
        await update.message.reply_text("Send comments (line by line):")

    elif step == "c_text":
        comments = text.strip().split("\n")
        qty = len(comments)

        price = (qty / 1000) * get_setting("comment_price")

        context.user_data["comments"] = "\n".join(comments)
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
            return await update.message.reply_text("Cancelled", reply_markup=main_menu())

        qty = context.user_data["qty"]
        price = context.user_data["price"]

        if balance < price:
            return await update.message.reply_text("Low balance")

        res = requests.post(COMMENT_API_URL, data={
            "key": COMMENT_API_KEY,
            "action": "add",
            "service": COMMENT_SERVICE_ID,
            "link": context.user_data["link"],
            "comments": context.user_data["comments"]
        }).json()

        if "order" in res:
            update_balance(tg_id, -price)

            cursor.execute("INSERT INTO orders VALUES (?, ?, ?, ?, ?)",
                           (res["order"], tg_id, "comments", context.user_data["link"], qty))
            conn.commit()

            await update.message.reply_text(
                f"✅ Order Placed\nID: {res['order']}",
                reply_markup=main_menu()
            )
        else:
            await bot.send_message(ADMIN_ID, f"COMMENT ERROR: {res}")
            await update.message.reply_text("Order Failed", reply_markup=main_menu())

        user_steps[tg_id] = None

    elif text == "📦 Orders":
        cursor.execute("SELECT * FROM orders WHERE telegram_id=?", (tg_id,))
        rows = cursor.fetchall()

        msg = "Orders:\n"
        for r in rows[-5:]:
            msg += f"{r[2]} | {r[4]} | {r[0]}\n"

        await update.message.reply_text(msg)

# ===== ADMIN =====
async def setprice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat_id != ADMIN_ID:
        return

    service = context.args[0]
    price = context.args[1]

    key = "like_price" if service == "like" else "comment_price"

    cursor.execute("UPDATE settings SET value=? WHERE key=?", (price, key))
    conn.commit()

    await update.message.reply_text(f"{service} price updated to ₹{price}")

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

        asyncio.run(bot.send_message(tg_id, f"₹{amount} added"))

    return {"status": "ok"}

# ===== RUN =====
def start_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setprice", setprice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.run_polling()

def start_web():
    app_web.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    threading.Thread(target=start_web).start()
    start_bot()
