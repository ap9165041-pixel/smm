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
BOT_TOKEN = "8748370733:AAHmioo1yYD4GcozjnJVVsN8niakHDzmcnE"
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
    cur.execute("CREATE TABLE IF NOT EXISTS users (telegram_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0)")
    cur.execute("CREATE TABLE IF NOT EXISTS payments (payment_id TEXT PRIMARY KEY, telegram_id INTEGER, amount REAL)")
    cur.execute("CREATE TABLE IF NOT EXISTS orders (order_id TEXT, telegram_id INTEGER, service TEXT, link TEXT, quantity INTEGER)")
    conn.commit()
    conn.close()

init_db()

# ===== BALANCE =====
def get_balance(tg):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE telegram_id=?", (tg,))
    r = cur.fetchone()

    if not r:
        cur.execute("INSERT INTO users VALUES (?,0)", (tg,))
        conn.commit()
        conn.close()
        return 0

    bal = r[0]
    conn.close()
    return bal

def update_balance(tg, amt):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = balance + ? WHERE telegram_id=?", (amt, tg))
    conn.commit()
    conn.close()

# ===== PAYMENT =====
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

def save_order(order_id, tg, service, link, qty):
    conn = db()
    cur = conn.cursor()
    cur.execute("INSERT INTO orders VALUES (?,?,?,?,?)", (order_id, tg, service, link, qty))
    conn.commit()
    conn.close()

# ===== UI =====
user_steps = {}

def main_menu():
    return ReplyKeyboardMarkup(
        [
            ["📊 Dashboard", "💳 Add Funds"],
            ["🚀 Services", "📦 My Orders"],
            ["🆘 Support"]
        ],
        resize_keyboard=True
    )

def services_menu():
    return ReplyKeyboardMarkup(
        [
            ["👍 Instagram Likes"],
            ["💬 Instagram Comments"],
            ["⬅️ Back"]
        ],
        resize_keyboard=True
    )

def confirm_kb():
    return ReplyKeyboardMarkup(
        [["✅ Place Order", "❌ Cancel"]],
        resize_keyboard=True
    )

BACK = ReplyKeyboardMarkup([["⬅️ Back"]], resize_keyboard=True)

# ===== TELEGRAM =====
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.message.chat_id
    bal = get_balance(tg)

    await update.message.reply_text(
        f"✨ Welcome\n\n👤 ID: {tg}\n💰 Balance: ₹{bal}",
        reply_markup=main_menu()
    )

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.message.chat_id
    text = update.message.text
    step = user_steps.get(tg)

    if text == "⬅️ Back":
        user_steps[tg] = None
        return await update.message.reply_text("Main Menu", reply_markup=main_menu())

    if text == "📊 Dashboard":
        return await update.message.reply_text(f"💰 Balance: ₹{get_balance(tg)}")

    if text == "💳 Add Funds":
        user_steps[tg] = "amount"
        return await update.message.reply_text("Enter amount:", reply_markup=BACK)

    if step == "amount":
        amt = int(text)
        link = client.payment_link.create({
            "amount": amt * 100,
            "currency": "INR",
            "notes": {"telegram_id": str(tg)}
        })
        user_steps[tg] = None
        return await update.message.reply_text(link['short_url'])

    if text == "🚀 Services":
        return await update.message.reply_text("Select:", reply_markup=services_menu())

    if "👍 Instagram Likes" in text:
        user_steps[tg] = "l1"
        return await update.message.reply_text("Send link:")

    if step == "l1":
        context.user_data["link"] = text
        user_steps[tg] = "l2"
        return await update.message.reply_text("Quantity:")

    if step == "l2":
        qty = int(text)
        price = (qty / 1000) * 29
        context.user_data["qty"] = qty
        context.user_data["price"] = price
        user_steps[tg] = "l3"
        return await update.message.reply_text(f"{qty} Likes = ₹{price}", reply_markup=confirm_kb())

    if step == "l3":
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
            await update.message.reply_text("✅ Order placed", reply_markup=main_menu())

        user_steps[tg] = None

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

# ===== FLASK =====
app = Flask(__name__)

# ✅ FIXED TELEGRAM WEBHOOK (NO EVENT LOOP BUG)
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, telegram_app.bot)

    asyncio.run(telegram_app.process_update(update))

    return "ok"

# ✅ WORKING PAYMENT WEBHOOK (FROM YOUR OLD CODE)
@app.route("/webhook", methods=["POST"])
def razorpay_webhook():
    print("🔥 PAYMENT HIT")

    body = request.data
    sig = request.headers.get("X-Razorpay-Signature")

    gen = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(gen, sig):
        print("❌ Invalid Signature")
        return {"status": "invalid"}, 400

    data = request.json
    print(data)

    if data.get("event") == "payment_link.paid":
        entity = data["payload"]["payment_link"]["entity"]

        tg = int(entity["notes"]["telegram_id"])
        amt = entity["amount_paid"] / 100
        pid = entity["id"]

        if payment_exists(pid):
            return {"status": "duplicate"}

        update_balance(tg, amt)
        save_payment(pid, tg, amt)

        requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            params={"chat_id": tg, "text": f"✅ ₹{amt} added"}
        )

    return {"status": "ok"}

# ===== START =====
if __name__ == "__main__":
    # Set webhook
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={APP_URL}/{BOT_TOKEN}")

    print("✅ BOT STARTED WITH WEBHOOK")

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
