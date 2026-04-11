import requests
import razorpay
import sqlite3
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

# ===== DATABASE (PERMANENT) =====
if not os.path.exists("data"):
    os.makedirs("data")

conn = sqlite3.connect("data/users.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS users (telegram_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0)")
cursor.execute("CREATE TABLE IF NOT EXISTS orders (order_id TEXT, telegram_id INTEGER, service TEXT, qty INTEGER)")
cursor.execute("CREATE TABLE IF NOT EXISTS payments (payment_id TEXT PRIMARY KEY, telegram_id INTEGER, amount REAL)")
conn.commit()

# ===== USER =====
def get_balance(tg_id):
    cursor.execute("SELECT balance FROM users WHERE telegram_id=?", (tg_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute("INSERT INTO users (telegram_id) VALUES (?)", (tg_id,))
        conn.commit()
        return 0
    return user[0]

def update_balance(tg_id, amount):
    cursor.execute("UPDATE users SET balance = balance + ? WHERE telegram_id=?", (amount, tg_id))
    conn.commit()

# ===== MENUS =====
def main_menu():
    return ReplyKeyboardMarkup([
        ["👤 Account", "💰 Recharge"],
        ["📦 Orders", "🛒 Services"]
    ], resize_keyboard=True)

def service_menu():
    return ReplyKeyboardMarkup([
        ["👍 Likes", "💬 Comments"],
        ["🔙 Back"]
    ], resize_keyboard=True)

# ===== STATE =====
user_steps = {}

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.message.chat_id
    balance = get_balance(tg_id)

    await update.message.reply_text(
        f"✨ Welcome to Cherap SMM Service 🚀\n\n🆔 ID: {tg_id}",
        reply_markup=main_menu()
    )

# ===== ADMIN =====
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat_id != ADMIN_ID:
        return

    keyboard = [
        ["👥 Users", "💰 Total Balance"],
        ["➕ Add Balance"],
        ["🔙 Back"]
    ]

    await update.message.reply_text("👑 Admin Panel", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

# ===== HANDLER =====
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.message.chat_id
    text = update.message.text
    balance = get_balance(tg_id)

    # BACK
    if text == "🔙 Back":
        user_steps[tg_id] = None
        return await update.message.reply_text("Main Menu", reply_markup=main_menu())

    # ACCOUNT
    if text == "👤 Account":
        return await update.message.reply_text(f"💰 Balance: ₹{balance}")

    # RECHARGE
    elif text == "💰 Recharge":
        user_steps[tg_id] = "amount"
        return await update.message.reply_text("Enter amount:")

    elif user_steps.get(tg_id) == "amount":
        if not text.isdigit():
            return await update.message.reply_text("❌ Enter number")

        amount = int(text)

        link = client.payment_link.create({
            "amount": amount * 100,
            "currency": "INR",
            "notes": {"telegram_id": str(tg_id)}
        })

        user_steps[tg_id] = None
        return await update.message.reply_text(f"💳 Pay:\n{link['short_url']}")

    # SERVICES
    elif text == "🛒 Services":
        return await update.message.reply_text("Select Service:", reply_markup=service_menu())

    # ===== LIKES =====
    elif text == "👍 Likes":
        user_steps[tg_id] = "like_link"
        return await update.message.reply_text(
            "🔥 Youtube Likes [No Drop] [Instant]\n💰 ₹25 / 1000\n📉 Min: 100\n\nSend Link:"
        )

    elif user_steps.get(tg_id) == "like_link":
        context.user_data["link"] = text
        user_steps[tg_id] = "like_qty"
        return await update.message.reply_text("Enter Quantity:")

    elif user_steps.get(tg_id) == "like_qty":
        qty = int(text)
        price = (qty / 1000) * 25

        if balance < price:
            return await update.message.reply_text("❌ Low Balance")

        update_balance(tg_id, -price)

        res = requests.post(LIKE_API_URL, data={
            "key": LIKE_API_KEY,
            "action": "add",
            "service": LIKE_SERVICE_ID,
            "link": context.user_data["link"],
            "quantity": qty
        }).json()

        if "order" in res:
            cursor.execute("INSERT INTO orders VALUES (?, ?, ?, ?)", (res["order"], tg_id, "Likes", qty))
            conn.commit()
            await update.message.reply_text(f"✅ Order ID: {res['order']}")

        user_steps[tg_id] = None

    # ===== COMMENTS =====
    elif text == "💬 Comments":
        user_steps[tg_id] = "c_link"
        return await update.message.reply_text(
            "💬 Youtube Custom Comments (Instant)\n💰 ₹170 / 1000\n📉 Min: 10\n\nSend Link:"
        )

    elif user_steps.get(tg_id) == "c_link":
        context.user_data["link"] = text
        user_steps[tg_id] = "c_text"
        return await update.message.reply_text("Send Comment Text:")

    elif user_steps.get(tg_id) == "c_text":
        context.user_data["comment"] = text
        user_steps[tg_id] = "c_qty"
        return await update.message.reply_text("Enter Quantity:")

    elif user_steps.get(tg_id) == "c_qty":
        qty = int(text)
        price = (qty / 1000) * 170

        if balance < price:
            return await update.message.reply_text("❌ Low Balance")

        update_balance(tg_id, -price)

        res = requests.post(COMMENT_API_URL, data={
            "key": COMMENT_API_KEY,
            "action": "add",
            "service": COMMENT_SERVICE_ID,
            "link": context.user_data["link"],
            "comments": context.user_data["comment"],
            "quantity": qty
        }).json()

        if "order" in res:
            cursor.execute("INSERT INTO orders VALUES (?, ?, ?, ?)", (res["order"], tg_id, "Comments", qty))
            conn.commit()
            await update.message.reply_text(f"✅ Order ID: {res['order']}")

        user_steps[tg_id] = None

    # ===== ORDERS =====
    elif text == "📦 Orders":
        cursor.execute("SELECT * FROM orders WHERE telegram_id=?", (tg_id,))
        data = cursor.fetchall()

        if not data:
            return await update.message.reply_text("No Orders Found")

        msg = "📦 Orders:\n\n"
        for d in data[-5:]:
            msg += f"{d[2]} | {d[3]} | ID: {d[0]}\n"

        return await update.message.reply_text(msg)

    # ===== ADMIN =====
    elif text == "👥 Users" and tg_id == ADMIN_ID:
        cursor.execute("SELECT COUNT(*) FROM users")
        total = cursor.fetchone()[0]
        return await update.message.reply_text(f"Users: {total}")

    elif text == "💰 Total Balance" and tg_id == ADMIN_ID:
        cursor.execute("SELECT SUM(balance) FROM users")
        total = cursor.fetchone()[0] or 0
        return await update.message.reply_text(f"₹{total}")

    elif text == "➕ Add Balance" and tg_id == ADMIN_ID:
        user_steps[tg_id] = "admin_user"
        return await update.message.reply_text("Enter Telegram ID:")

    elif user_steps.get(tg_id) == "admin_user":
        context.user_data["target"] = int(text)
        user_steps[tg_id] = "admin_amount"
        return await update.message.reply_text("Enter Amount:")

    elif user_steps.get(tg_id) == "admin_amount":
        update_balance(context.user_data["target"], float(text))
        user_steps[tg_id] = None
        return await update.message.reply_text("✅ Balance Added")

# ===== WEBHOOK =====
app_web = Flask(__name__)

@app_web.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    if data.get("event") == "payment_link.paid":
        payment = data["payload"]["payment"]["entity"]
        payment_id = payment["id"]

        cursor.execute("SELECT * FROM payments WHERE payment_id=?", (payment_id,))
        if cursor.fetchone():
            return {"status": "duplicate"}

        tg_id = int(payment["notes"]["telegram_id"])
        amount = payment["amount"] / 100

        update_balance(tg_id, amount)

        cursor.execute("INSERT INTO payments VALUES (?, ?, ?)", (payment_id, tg_id, amount))
        conn.commit()

        asyncio.run(bot.send_message(chat_id=tg_id, text=f"✅ ₹{amount} added"))

    return {"status": "ok"}

# ===== RUN =====
async def start_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # 🔥 IMPORTANT FIX
    await app.bot.delete_webhook(drop_pending_updates=True)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    print("✅ Bot Running...")
    await app.run_polling()

def start_web():
    app_web.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    threading.Thread(target=start_web).start()

    import asyncio
    asyncio.run(start_bot())
