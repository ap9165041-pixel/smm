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

# ================= STATE =================
user_steps = {}

def main_menu():
    return ReplyKeyboardMarkup(
        [
            ["👤 Account", "💰 Recharge"],
            ["📦 Orders", "🛒 Services"]
        ],
        resize_keyboard=True
    )

BACK_KB = ReplyKeyboardMarkup([["⬅️ Back"]], resize_keyboard=True)

# ================= USER =================
def get_user(tg_id):
    cursor.execute("SELECT id, balance FROM users WHERE telegram_id=?", (tg_id,))
    user = cursor.fetchone()

    if not user:
        cursor.execute("INSERT INTO users (telegram_id) VALUES (?)", (tg_id,))
        conn.commit()
        return get_user(tg_id)

    return user

def update_balance(tg_id, amount):
    cursor.execute(
        "UPDATE users SET balance = balance + ? WHERE telegram_id=?",
        (amount, tg_id)
    )
    conn.commit()

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.message.chat_id
    user_id, balance = get_user(tg_id)

    await update.message.reply_text(
        f"✨ Welcome SMM Bot 🚀\n🆔 ID: {user_id}\n💰 Balance: ₹{balance}",
        reply_markup=main_menu()
    )

# ================= SERVICES =================
async def services_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("👍 Likes - ₹25/1000", callback_data="likes")],
        [InlineKeyboardButton("💬 Comments - ₹250/1000", callback_data="comments")]
    ]

    await update.message.reply_text(
        "🔥 Select Service:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= CALLBACK =================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    tg_id = query.message.chat_id

    if query.data == "likes":
        user_steps[tg_id] = "like_link"
        await query.message.reply_text(
            "👍 Likes Selected\n💰 ₹25 / 1000\n\nSend Link:",
            reply_markup=BACK_KB
        )

    elif query.data == "comments":
        user_steps[tg_id] = "c_link"
        await query.message.reply_text(
            "💬 Comments Selected\n💰 ₹250 / 1000\n\nSend Link:",
            reply_markup=BACK_KB
        )

# ================= HANDLE =================
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.message.chat_id
    text = update.message.text

    user_id, balance = get_user(tg_id)
    step = user_steps.get(tg_id)

    if text == "⬅️ Back":
        user_steps[tg_id] = None
        await update.message.reply_text("🔙 Main Menu", reply_markup=main_menu())
        return

    # ACCOUNT
    if text == "👤 Account":
        await update.message.reply_text(f"🆔 ID: {user_id}\n💰 Balance: ₹{balance}")

    # RECHARGE
    elif text == "💰 Recharge":
        user_steps[tg_id] = "amount"
        await update.message.reply_text("Enter amount:", reply_markup=BACK_KB)

    elif step == "amount":
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
        await services_menu(update, context)

    # ================= LIKE FLOW =================
    elif step == "like_link":
        context.user_data["link"] = text
        user_steps[tg_id] = "like_qty"
        await update.message.reply_text("Enter Likes Quantity:")

    elif step == "like_qty":
        qty = int(text)

        if qty < 100:
            await update.message.reply_text("❌ Min 100")
            return

        price = round((qty / 1000) * 25, 2)

        if balance < price:
            await update.message.reply_text(f"❌ Low Balance ₹{price}")
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

        if "order" in res:
            cursor.execute("INSERT INTO orders VALUES (?, ?, ?, ?, ?)",
                           (res["order"], tg_id, "likes", context.user_data["link"], qty))
            conn.commit()

            await update.message.reply_text(
                f"✅ ORDER PLACED\n👍 Likes: {qty}\n💰 ₹{price}\n📦 ID: {res['order']}"
            )
        else:
            await update.message.reply_text("❌ Failed")

        user_steps[tg_id] = None

    # ================= COMMENTS (NEW ADVANCED SYSTEM) =================
    elif step == "c_link":
        context.user_data["link"] = text
        user_steps[tg_id] = "c_qty"
        await update.message.reply_text("💬 Enter Comment Count:")

    elif step == "c_qty":
        if not text.isdigit():
            await update.message.reply_text("❌ Number send karo")
            return

        qty = int(text)

        if qty < 10:
            await update.message.reply_text("❌ Minimum 10 comments")
            return

        price = round((qty / 1000) * 250, 2)

        context.user_data["comment_qty"] = qty
        context.user_data["comment_price"] = price

        user_steps[tg_id] = "c_confirm"

        await update.message.reply_text(
            f"📦 ORDER SUMMARY\n\n"
            f"💬 Comments: {qty}\n"
            f"💰 Rate: ₹250 / 1000\n"
            f"💳 Total: ₹{price}\n\n"
            f"👉 Type YES to confirm or NO to cancel"
        )

    elif step == "c_confirm":
        if text.lower() == "no":
            user_steps[tg_id] = None
            await update.message.reply_text("❌ Cancelled")
            return

        if text.lower() != "yes":
            await update.message.reply_text("👉 YES or NO only")
            return

        qty = context.user_data["comment_qty"]
        price = context.user_data["comment_price"]

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
            "comments": qty
        }).json()

        if "order" in res:
            cursor.execute("INSERT INTO orders VALUES (?, ?, ?, ?, ?)",
                           (res["order"], tg_id, "comments", context.user_data["link"], qty))
            conn.commit()

            await update.message.reply_text(
                f"✅ ORDER PLACED\n💬 Comments: {qty}\n💰 ₹{price}\n📦 ID: {res['order']}"
            )
        else:
            await update.message.reply_text("❌ Failed")

        user_steps[tg_id] = None

    # ORDERS
    elif text == "📦 Orders":
        cursor.execute("SELECT * FROM orders WHERE telegram_id=?", (tg_id,))
        rows = cursor.fetchall()

        if not rows:
            await update.message.reply_text("No orders")
            return

        msg = "📦 LAST ORDERS:\n"
        for r in rows[-5:]:
            msg += f"{r[2]} | {r[4]} | {r[0]}\n"

        await update.message.reply_text(msg)

# ================= WEBHOOK =================
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
        entity = data["payload"]["payment_link"]["entity"]

        tg_id = int(entity["notes"]["telegram_id"])
        amount = entity["amount_paid"] / 100
        payment_id = entity["id"]

        cursor.execute("SELECT * FROM payments WHERE payment_id=?", (payment_id,))
        if cursor.fetchone():
            return {"status": "duplicate"}

        update_balance(tg_id, amount)

        cursor.execute("INSERT INTO payments VALUES (?, ?, ?)",
                       (payment_id, tg_id, amount))
        conn.commit()

        asyncio.run(bot.send_message(tg_id, f"✅ ₹{amount} Added"))

    return {"status": "ok"}

# ================= RUN =================
def start_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    app.run_polling()

def start_web():
    app_web.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

if __name__ == "__main__":
    threading.Thread(target=start_web).start()
    start_bot()
