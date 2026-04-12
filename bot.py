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

    conn.close()
    return r[0]

def update_balance(tg, amt):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = balance + ? WHERE telegram_id=?", (amt, tg))
    conn.commit()
    conn.close()

# ===== PAYMENTS =====
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

def get_orders(tg):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT service, link, quantity FROM orders WHERE telegram_id=?", (tg,))
    rows = cur.fetchall()
    conn.close()
    return rows

# ===== UI =====
user_steps = {}

def main_menu():
    return ReplyKeyboardMarkup(
        [
            ["🛒 Order Services", "💰 Add Balance"],
            ["👤 My Account", "📦 My Orders"],
            ["🎧 Support"]
        ],
        resize_keyboard=True
    )

def confirm_kb():
    return ReplyKeyboardMarkup([["✅ Confirm", "❌ Cancel"]], resize_keyboard=True)

BACK = ReplyKeyboardMarkup([["⬅️ Back"]], resize_keyboard=True)

# ===== TELEGRAM =====
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.message.chat_id
    bal = get_balance(tg)

    text = f"""
🚀 *Welcome to Premium SMM Panel*

💎 Fast • Secure • Trusted

━━━━━━━━━━━━━━━
👤 ID: `{tg}`
💰 Balance: ₹{bal}
━━━━━━━━━━━━━━━

🔥 Services:
• 👍 Likes
• 💬 Comments

Use menu below 👇
"""
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu())

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.message.chat_id
    text = update.message.text
    step = user_steps.get(tg)

    if text == "⬅️ Back":
        user_steps[tg] = None
        return await update.message.reply_text("Main Menu", reply_markup=main_menu())

    # ===== ACCOUNT =====
    if text == "👤 My Account":
        bal = get_balance(tg)
        return await update.message.reply_text(
            f"👤 ID: `{tg}`\n💰 Balance: ₹{bal}",
            parse_mode="Markdown"
        )

    # ===== SUPPORT =====
    if text == "🎧 Support":
        return await update.message.reply_text(
            f"Contact Admin:\n👉 @yourusername\nID: `{ADMIN_ID}`",
            parse_mode="Markdown"
        )

    # ===== ORDERS =====
    if text == "📦 My Orders":
        orders = get_orders(tg)

        if not orders:
            return await update.message.reply_text("No orders yet")

        msg = "📦 Orders:\n\n"
        for o in orders[-10:]:
            msg += f"{o[0]} | {o[2]}\n{o[1]}\n\n"

        return await update.message.reply_text(msg)

    # ===== ADD BALANCE =====
    if text == "💰 Add Balance":
        user_steps[tg] = "amount"
        return await update.message.reply_text("Enter amount:", reply_markup=BACK)

    if step == "amount":
        if not text.isdigit():
            return await update.message.reply_text("Enter valid amount")

        amt = int(text)

        link = client.payment_link.create({
            "amount": amt * 100,
            "currency": "INR",
            "notes": {"telegram_id": str(tg)}
        })

        user_steps[tg] = None
        return await update.message.reply_text(link['short_url'])

    # ===== SERVICES =====
    if text == "🛒 Order Services":
        return await update.message.reply_text(
            "Choose service:",
            reply_markup=ReplyKeyboardMarkup(
                [["👍 Likes"], ["💬 Comments"], ["⬅️ Back"]],
                resize_keyboard=True
            )
        )

    # ===== LIKES FLOW =====
    if text == "👍 Likes":
        user_steps[tg] = "l1"
        return await update.message.reply_text("Send link:", reply_markup=BACK)

    if step == "l1":
        context.user_data["link"] = text
        user_steps[tg] = "l2"
        return await update.message.reply_text("Enter quantity:")

    if step == "l2":
        if not text.isdigit():
            return await update.message.reply_text("Invalid")

        qty = int(text)
        price = (qty / 1000) * 29

        context.user_data["qty"] = qty
        context.user_data["price"] = price

        user_steps[tg] = "l3"
        return await update.message.reply_text(
            f"Qty: {qty}\nPrice: ₹{round(price,2)}",
            reply_markup=confirm_kb()
        )

    if step == "l3":
        if text == "❌ Cancel":
            user_steps[tg] = None
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
            await update.message.reply_text("✅ Order placed", reply_markup=main_menu())
        else:
            await update.message.reply_text("❌ Failed", reply_markup=main_menu())

        user_steps[tg] = None

# ===== HANDLERS =====
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

# ===== FLASK =====
app = Flask(__name__)

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, telegram_app.bot)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    loop.run_until_complete(telegram_app.initialize())
    loop.run_until_complete(telegram_app.process_update(update))

    return "ok"

@app.route("/webhook", methods=["POST"])
def razorpay_webhook():
    body = request.data
    sig = request.headers.get("X-Razorpay-Signature")

    gen = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(gen, sig):
        return {"status": "invalid"}, 400

    data = request.json

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
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={APP_URL}/{BOT_TOKEN}")

    print("BOT STARTED")

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
