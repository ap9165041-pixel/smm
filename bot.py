import requests
import razorpay
import sqlite3
import hmac
import hashlib
import os
import asyncio
import threading
from flask import Flask, request

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

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

# ===== DB =====
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS users(
id INTEGER PRIMARY KEY AUTOINCREMENT,
telegram_id INTEGER UNIQUE,
balance REAL DEFAULT 0,
banned INTEGER DEFAULT 0
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS wallet_history(
id INTEGER PRIMARY KEY AUTOINCREMENT,
tg_id INTEGER,
amount REAL,
type TEXT
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS orders(
order_id TEXT,
tg_id INTEGER,
service TEXT,
status TEXT
)""")

conn.commit()

user_state = {}
order_cache = {}

# ===== HELPERS =====
def is_banned(tg_id):
    cursor.execute("SELECT banned FROM users WHERE telegram_id=?", (tg_id,))
    r = cursor.fetchone()
    return r and r[0] == 1

def get_user(tg_id):
    cursor.execute("SELECT id, balance FROM users WHERE telegram_id=?", (tg_id,))
    user = cursor.fetchone()

    if not user:
        cursor.execute("INSERT INTO users (telegram_id) VALUES (?)", (tg_id,))
        conn.commit()
        return get_user(tg_id)

    return user

def update_balance(tg_id, amount, ttype="add"):
    if ttype == "add":
        cursor.execute("UPDATE users SET balance = balance + ? WHERE telegram_id=?", (amount, tg_id))
    else:
        cursor.execute("UPDATE users SET balance = balance - ? WHERE telegram_id=?", (amount, tg_id))

    cursor.execute("INSERT INTO wallet_history (tg_id, amount, type) VALUES (?, ?, ?)",
                   (tg_id, amount, ttype))
    conn.commit()

# ===== INLINE MENUS =====
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Account", callback_data="acc"),
         InlineKeyboardButton("💰 Wallet", callback_data="wallet")],

        [InlineKeyboardButton("🛒 Services", callback_data="services"),
         InlineKeyboardButton("📦 Orders", callback_data="orders")]
    ])

def service_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👍 Likes", callback_data="likes")],
        [InlineKeyboardButton("💬 Comments", callback_data="comments")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back")]
    ])

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.message.chat_id
    user_id, balance = get_user(tg_id)

    await update.message.reply_text(
        f"🚀 Welcome SMM Bot\nID: {user_id}\nBalance: ₹{balance}",
        reply_markup=main_menu()
    )

# ===== BUTTON HANDLER =====
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    tg_id = query.message.chat_id
    data = query.data

    if is_banned(tg_id):
        await query.edit_message_text("🚫 You are banned")
        return

    user_id, balance = get_user(tg_id)

    # ===== ACCOUNT =====
    if data == "acc":
        await query.edit_message_text(f"ID: {user_id}\nBalance: ₹{balance}", reply_markup=main_menu())

    # ===== WALLET =====
    elif data == "wallet":
        cursor.execute("SELECT amount, type FROM wallet_history WHERE tg_id=?", (tg_id,))
        rows = cursor.fetchall()

        msg = "💰 Wallet History:\n"
        for r in rows[-10:]:
            msg += f"{r[1]} ₹{r[0]}\n"

        await query.edit_message_text(msg, reply_markup=main_menu())

    # ===== SERVICES =====
    elif data == "services":
        await query.edit_message_text("Select Service:", reply_markup=service_menu())

    # ===== BACK =====
    elif data == "back":
        await query.edit_message_text("Main Menu", reply_markup=main_menu())

    # ===== ORDERS =====
    elif data == "orders":
        cursor.execute("SELECT * FROM orders WHERE tg_id=?", (tg_id,))
        rows = cursor.fetchall()

        msg = "📦 Orders:\n"
        for r in rows[-10:]:
            msg += f"{r[0]} | {r[2]} | {r[3]}\n"

        await query.edit_message_text(msg, reply_markup=main_menu())

    # ===== LIKES =====
    elif data == "likes":
        user_state[tg_id] = "like_link"
        await query.edit_message_text("Send Video Link:")

    # ===== COMMENTS =====
    elif data == "comments":
        user_state[tg_id] = "c_link"
        await query.edit_message_text("Send Video Link:")

# ===== MESSAGE FLOW =====
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.message.chat_id
    text = update.message.text

    user_id, balance = get_user(tg_id)
    step = user_state.get(tg_id)

    # ===== LIKE FLOW =====
    if step == "like_link":
        context.user_data["link"] = text
        user_state[tg_id] = "like_qty"
        await update.message.reply_text("Enter Quantity:")

    elif step == "like_qty":
        qty = int(text)
        price = (qty / 1000) * 25

        if balance < price:
            await update.message.reply_text("❌ Low balance")
            return

        update_balance(tg_id, price, "sub")

        res = requests.post(LIKE_API_URL, data={
            "key": LIKE_API_KEY,
            "action": "add",
            "service": LIKE_SERVICE_ID,
            "link": context.user_data["link"],
            "quantity": qty
        }).json()

        order_id = res.get("order", "NA")

        cursor.execute("INSERT INTO orders VALUES (?, ?, ?, ?)",
                       (order_id, tg_id, "likes", "pending"))
        conn.commit()

        await update.message.reply_text(f"✅ Order: {order_id}")
        user_state[tg_id] = None

    # ===== COMMENTS SMART PRICING =====
    elif step == "c_link":
        context.user_data["link"] = text
        user_state[tg_id] = "c_text"
        await update.message.reply_text("Send Comment Text:")

    elif step == "c_text":
        context.user_data["comment"] = text
        user_state[tg_id] = "c_qty"
        await update.message.reply_text("Enter Quantity:")

    elif step == "c_qty":
        qty = int(text)

        price_per_1 = 170 / 1000
        price = qty * price_per_1

        if balance < price:
            await update.message.reply_text("❌ Low balance")
            return

        update_balance(tg_id, price, "sub")

        res = requests.post(COMMENT_API_URL, data={
            "key": COMMENT_API_KEY,
            "action": "add",
            "service": COMMENT_SERVICE_ID,
            "link": context.user_data["link"],
            "comments": context.user_data["comment"],
            "quantity": qty
        }).json()

        order_id = res.get("order", "NA")

        cursor.execute("INSERT INTO orders VALUES (?, ?, ?, ?)",
                       (order_id, tg_id, "comments", "pending"))
        conn.commit()

        await update.message.reply_text(f"✅ Order: {order_id}")
        user_state[tg_id] = None

# ===== ADMIN PANEL =====
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.message.chat_id

    if tg_id != ADMIN_ID:
        return

    cmd = context.args

    if len(cmd) < 2:
        await update.message.reply_text("Usage: /addbalance id amount")
        return

    target = int(cmd[0])
    amount = float(cmd[1])

    update_balance(target, amount, "add")
    await update.message.reply_text("✅ Balance Added")

# ===== FLASK WEBHOOK =====
app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    return {"status": "ok"}

# ===== RUN =====
def start_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addbalance", admin))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    app.run_polling()

def start_web():
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    threading.Thread(target=start_web).start()
    start_bot()
