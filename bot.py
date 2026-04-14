import requests
import razorpay
import sqlite3
import hmac
import hashlib
import os
import asyncio

from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ===== CONFIG =====
BOT_TOKEN = "8345172518:AAHahPKnJZwKZ-SIp97vBtNyMyyRXZ-Gw7M"
ADMIN_ID = 8451049817

LIKE_API_KEY = "7d01eb30166546130c171b26eecee191"
LIKE_API_URL = "https://tntsmm.in/api/v2"
LIKE_SERVICE_ID = "3062"

COMMENT_API_KEY = "a6a2e96cd415e968918b20baa261bc4b095f36c1"
COMMENT_API_URL = "https://smm-jupiter.com/api/v2"
COMMENT_SERVICE_ID = "13259"

RAZORPAY_KEY = "rzp_live_Sc7lXEOJ2ZWjPL"
RAZORPAY_SECRET = "KxRu3ssMBcNLTQ7LxMY0jZIQ"
WEBHOOK_SECRET = "ayush@123"

APP_URL = "https://smm-production-3fc3.up.railway.app" # 👈 CHANGE THIS

client = razorpay.Client(auth=(RAZORPAY_KEY, RAZORPAY_SECRET))

# ===== DB =====
def db():
    return sqlite3.connect("users.db", check_same_thread=False)

def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("CREATE TABLE IF NOT EXISTS users (telegram_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0, banned INTEGER DEFAULT 0)")
    cur.execute("CREATE TABLE IF NOT EXISTS payments (payment_id TEXT PRIMARY KEY, telegram_id INTEGER, amount REAL)")
    cur.execute("CREATE TABLE IF NOT EXISTS orders (order_id TEXT, telegram_id INTEGER, service TEXT, link TEXT, quantity INTEGER)")

    conn.commit()
    conn.close()

init_db()

# ===== HELPERS =====
def is_admin(user_id):
    return user_id == ADMIN_ID

def get_balance(tg):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE telegram_id=?", (tg,))
    r = cur.fetchone()

    if not r:
        cur.execute("INSERT INTO users (telegram_id) VALUES (?)", (tg,))
        conn.commit()
        conn.close()
        return 0

    conn.close()
    return r[0]

def update_balance(tg, amt):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = balance + ? WHERE telegram_id=?", (amt, tg))
    conn.commit()
    conn.close()

def save_order(order_id, tg, service, link, qty):
    conn = db()
    cur = conn.cursor()
    cur.execute("INSERT INTO orders VALUES (?,?,?,?,?)", (order_id, tg, service, link, qty))
    conn.commit()
    conn.close()

def payment_exists(pid):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM payments WHERE payment_id=?", (pid,))
    r = cur.fetchone()
    conn.close()
    return r is not None

def save_payment(pid, tg, amt):
    conn = db()
    cur = conn.cursor()
    cur.execute("INSERT INTO payments VALUES (?,?,?)", (pid, tg, amt))
    conn.commit()
    conn.close()

# ===== UI =====
user_steps = {}

def main_menu():
    return ReplyKeyboardMarkup([
        ["👤 Account", "💰 Recharge"],
        ["📦 Orders", "🛒 Services"],
        ["🎧 Support"]
    ], resize_keyboard=True)

def services_menu():
    return ReplyKeyboardMarkup([
        ["👍 Likes (₹29/1000)", "💬 Comments (₹250/1000)"],
        ["⬅️ Back"]
    ], resize_keyboard=True)

def confirm_kb():
    return ReplyKeyboardMarkup([["✅ Confirm", "❌ Cancel"]], resize_keyboard=True)

BACK = ReplyKeyboardMarkup([["⬅️ Back"]], resize_keyboard=True)

# ===== TELEGRAM =====
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.message.chat_id
    bal = get_balance(tg)

    await update.message.reply_text(
        f"🔥 Welcome\n💰 Balance: ₹{bal}",
        reply_markup=main_menu()
    )

# ===== ADMIN =====
async def check_balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.chat_id):
        return

    try:
        tg = int(context.args[0])
        bal = get_balance(tg)
        await update.message.reply_text(f"👤 {tg}\n💰 ₹{bal}")
    except:
        await update.message.reply_text("Usage: /checkbalance USER_ID")

# ===== MAIN HANDLER =====
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.message.chat_id
    text = update.message.text
    step = user_steps.get(tg)

    # BACK
    if text == "⬅️ Back":
        user_steps[tg] = None
        context.user_data.clear()
        return await update.message.reply_text("Main Menu", reply_markup=main_menu())

    elif text == "👤 Account":
        return await update.message.reply_text(f"💰 ₹{get_balance(tg)}")

    elif text == "🎧 Support":
        return await update.message.reply_text("Contact Admin")

    elif text == "🛒 Services":
        return await update.message.reply_text("Choose:", reply_markup=services_menu())

    # ===== LIKES =====
    elif text.startswith("👍 Likes"):
        user_steps[tg] = "l1"
        context.user_data.clear()
        return await update.message.reply_text("Send link:", reply_markup=BACK)

    elif step == "l1":
        context.user_data["link"] = text
        user_steps[tg] = "l2"
        return await update.message.reply_text("Enter quantity:")

    elif step == "l2":
        if not text.isdigit():
            return await update.message.reply_text("Invalid")

        qty = int(text)
        price = (qty / 1000) * 29

        context.user_data["qty"] = qty
        context.user_data["price"] = price

        user_steps[tg] = "l3"
        return await update.message.reply_text(f"{qty} Likes = ₹{price}", reply_markup=confirm_kb())

    elif step == "l3":
        if text == "❌ Cancel":
            user_steps[tg] = None
            context.user_data.clear()
            return await update.message.reply_text("Cancelled", reply_markup=main_menu())

        if get_balance(tg) < context.user_data["price"]:
            return await update.message.reply_text("Low balance")

        res = requests.post(LIKE_API_URL, data={
            "key": LIKE_API_KEY,
            "action": "add",
            "service": LIKE_SERVICE_ID,
            "link": context.user_data["link"],
            "quantity": context.user_data["qty"]
        }).json()

        if "order" in res:
            update_balance(tg, -context.user_data["price"])
            save_order(res["order"], tg, "likes", context.user_data["link"], context.user_data["qty"])

            # ADMIN ALERT
            requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", params={
                "chat_id": ADMIN_ID,
                "text": f"📦 Likes Order\nUser: {tg}\nQty: {context.user_data['qty']}"
            })

            user_steps[tg] = None
            context.user_data.clear()
            return await update.message.reply_text("Order placed", reply_markup=main_menu())

    # ===== COMMENTS =====
    elif text.startswith("💬 Comments"):
        user_steps[tg] = "c1"
        context.user_data.clear()
        return await update.message.reply_text("Send link:", reply_markup=BACK)

    elif step == "c1":
        context.user_data["link"] = text
        user_steps[tg] = "c2"
        return await update.message.reply_text("Send comments:")

    elif step == "c2":
        comments = text
        qty = len(comments.split("\n"))
        price = (qty / 1000) * 250

        context.user_data["comments"] = comments
        context.user_data["qty"] = qty
        context.user_data["price"] = price

        user_steps[tg] = "c3"
        return await update.message.reply_text(f"{qty} Comments = ₹{price}", reply_markup=confirm_kb())

    elif step == "c3":
        if text == "❌ Cancel":
            user_steps[tg] = None
            context.user_data.clear()
            return await update.message.reply_text("Cancelled", reply_markup=main_menu())

        if get_balance(tg) < context.user_data["price"]:
            return await update.message.reply_text("Low balance")

        res = requests.post(COMMENT_API_URL, data={
            "key": COMMENT_API_KEY,
            "action": "add",
            "service": COMMENT_SERVICE_ID,
            "link": context.user_data["link"],
            "comments": context.user_data["comments"]
        }).json()

        if "order" in res:
            update_balance(tg, -context.user_data["price"])
            save_order(res["order"], tg, "comments", context.user_data["link"], context.user_data["qty"])

            requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", params={
                "chat_id": ADMIN_ID,
                "text": f"📦 Comment Order\nUser: {tg}\nQty: {context.user_data['qty']}"
            })

            user_steps[tg] = None
            context.user_data.clear()
            return await update.message.reply_text("Order placed", reply_markup=main_menu())

# ===== HANDLERS =====
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("checkbalance", check_balance_cmd))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

# ===== FLASK =====
app = Flask(__name__)

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    loop.run_until_complete(telegram_app.initialize())
    loop.run_until_complete(telegram_app.process_update(update))

    return "ok"

# ===== START =====
if __name__ == "__main__":
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={APP_URL}/{BOT_TOKEN}")

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
