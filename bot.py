import requests
import razorpay
import sqlite3
import hmac
import hashlib
import os
from flask import Flask, request, jsonify
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import threading

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


client = razorpay.Client(auth=(RAZORPAY_KEY, RAZORPAY_SECRET))
DB_PATH = "users.db"
DB_LOCK = threading.Lock()

# ===== DB INIT =====
def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn

def init_db():
    with DB_LOCK:
        conn = db()
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS users (telegram_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0)")
        cur.execute("CREATE TABLE IF NOT EXISTS payments (payment_id TEXT PRIMARY KEY, telegram_id INTEGER, amount REAL)")
        cur.execute("CREATE TABLE IF NOT EXISTS orders (order_id TEXT, telegram_id INTEGER, service TEXT, link TEXT, quantity INTEGER)")
        conn.commit()
        conn.close()

init_db()

# ===== DB SAFE FUNCTIONS =====
def ensure_user(tg):
    with DB_LOCK:
        conn = db()
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO users (telegram_id, balance) VALUES (?, 0)", (tg,))
        conn.commit()
        conn.close()

def get_balance(tg):
    with DB_LOCK:
        conn = db()
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO users (telegram_id, balance) VALUES (?, 0)", (tg,))
        cur.execute("SELECT balance FROM users WHERE telegram_id=?", (tg,))
        r = cur.fetchone()
        conn.commit()
        conn.close()
        return round(r[0] if r else 0, 2)

def update_balance(tg, amt):
    with DB_LOCK:
        conn = db()
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO users (telegram_id, balance) VALUES (?, 0)", (tg,))
        cur.execute("UPDATE users SET balance = balance + ? WHERE telegram_id=?", (amt, tg))
        conn.commit()
        conn.close()

def payment_exists(pid):
    with DB_LOCK:
        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM payments WHERE payment_id=?", (pid,))
        r = cur.fetchone()
        conn.close()
        return r is not None

def save_payment(pid, tg, amt):
    with DB_LOCK:
        conn = db()
        cur = conn.cursor()
        cur.execute("INSERT INTO payments (payment_id, telegram_id, amount) VALUES (?,?,?)", (pid, tg, amt))
        conn.commit()
        conn.close()

def save_order(order_id, tg, service, link, qty):
    with DB_LOCK:
        conn = db()
        cur = conn.cursor()
        cur.execute("INSERT INTO orders (order_id, telegram_id, service, link, quantity) VALUES (?,?,?,?,?)", (order_id, tg, service, link, qty))
        conn.commit()
        conn.close()

# ===== UI =====
user_steps = {}

def main_menu():
    return ReplyKeyboardMarkup(
        [["👤 Account", "💰 Recharge"],
         ["📦 Orders", "🛒 Services"]],
        resize_keyboard=True
    )

def services_menu():
    return ReplyKeyboardMarkup(
        [["👍 Likes (₹29/1000)", "💬 Comments (₹250/1000)"],
         ["⬅️ Back"]],
        resize_keyboard=True
    )

def confirm_kb():
    return ReplyKeyboardMarkup([["✅ Confirm", "❌ Cancel"]], resize_keyboard=True)

BACK = ReplyKeyboardMarkup([["⬅️ Back"]], resize_keyboard=True)

# ===== BOT =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_chat.id
    ensure_user(tg)
    await update.message.reply_text(f"💰 Balance: ₹{get_balance(tg)}", reply_markup=main_menu())

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_chat.id
    text = (update.message.text or "").strip()
    step = user_steps.get(tg)
    ensure_user(tg)

    if text == "⬅️ Back":
        user_steps[tg] = None
        context.user_data.clear()
        return await update.message.reply_text("Main Menu", reply_markup=main_menu())

    if text == "👤 Account":
        return await update.message.reply_text(f"💰 ₹{get_balance(tg)}", reply_markup=main_menu())

    if text == "💰 Recharge":
        user_steps[tg] = "amount"
        return await update.message.reply_text("Enter amount:", reply_markup=BACK)

    if step == "amount":
        if not text.isdigit() or int(text) <= 0:
            return await update.message.reply_text("Enter valid amount")

        amt = int(text)
        link = client.payment_link.create({
            "amount": amt * 100,
            "currency": "INR",
            "notes": {"telegram_id": str(tg)}
        })

        user_steps[tg] = None
        return await update.message.reply_text(link["short_url"], reply_markup=main_menu())

    if text == "🛒 Services":
        return await update.message.reply_text("Choose:", reply_markup=services_menu())

    if "👍 Likes" in text:
        user_steps[tg] = "l1"
        return await update.message.reply_text("Send link:", reply_markup=BACK)

    if step == "l1":
        context.user_data["link"] = text
        user_steps[tg] = "l2"
        return await update.message.reply_text("Enter quantity (Min 50):", reply_markup=BACK)

    if step == "l2":
        if not text.isdigit():
            return await update.message.reply_text("Invalid quantity")

        qty = int(text)
        if qty < 50:
            return await update.message.reply_text("❌ Minimum 50 likes")

        price = round((qty / 1000) * 29, 2)
        context.user_data["qty"] = qty
        context.user_data["price"] = price
        user_steps[tg] = "l3"
        return await update.message.reply_text(f"{qty} Likes = ₹{price}\nConfirm?", reply_markup=confirm_kb())

    if step == "l3":
        if text == "❌ Cancel":
            user_steps[tg] = None
            context.user_data.clear()
            return await update.message.reply_text("Cancelled", reply_markup=main_menu())

        if text != "✅ Confirm":
            return await update.message.reply_text("Please choose Confirm or Cancel", reply_markup=confirm_kb())

        if get_balance(tg) < context.user_data.get("price", 0):
            user_steps[tg] = None
            context.user_data.clear()
            return await update.message.reply_text("Low balance", reply_markup=main_menu())

        try:
            res = requests.post(LIKE_API_URL, data={
                "key": LIKE_API_KEY,
                "action": "add",
                "service": LIKE_SERVICE_ID,
                "link": context.user_data["link"],
                "quantity": context.user_data["qty"]
            }, timeout=30).json()
        except Exception:
            user_steps[tg] = None
            context.user_data.clear()
            return await update.message.reply_text("❌ API Error", reply_markup=main_menu())

        if "order" in res:
            update_balance(tg, -context.user_data["price"])
            save_order(str(res["order"]), tg, "likes", context.user_data["link"], context.user_data["qty"])
            await update.message.reply_text("✅ Order Placed", reply_markup=main_menu())
        else:
            await update.message.reply_text("❌ Failed", reply_markup=main_menu())

        user_steps[tg] = None
        context.user_data.clear()
        return

    if "💬 Comments" in text:
        user_steps[tg] = "c1"
        return await update.message.reply_text("Send link:", reply_markup=BACK)

    if step == "c1":
        context.user_data["link"] = text
        user_steps[tg] = "c2"
        return await update.message.reply_text("Send comments (line by line):", reply_markup=BACK)

    if step == "c2":
        comments = [c.strip() for c in text.split("\n") if c.strip()]
        qty = len(comments)

        if qty < 10:
            return await update.message.reply_text("❌ Minimum 10 comments")

        price = round((qty / 1000) * 250, 2)
        context.user_data["comments"] = "\n".join(comments)
        context.user_data["qty"] = qty
        context.user_data["price"] = price
        user_steps[tg] = "c3"
        return await update.message.reply_text(f"{qty} Comments = ₹{price}\nConfirm?", reply_markup=confirm_kb())

    if step == "c3":
        if text == "❌ Cancel":
            user_steps[tg] = None
            context.user_data.clear()
            return await update.message.reply_text("Cancelled", reply_markup=main_menu())

        if text != "✅ Confirm":
            return await update.message.reply_text("Please choose Confirm or Cancel", reply_markup=confirm_kb())

        if get_balance(tg) < context.user_data.get("price", 0):
            user_steps[tg] = None
            context.user_data.clear()
            return await update.message.reply_text("Low balance", reply_markup=main_menu())

        try:
            res = requests.post(COMMENT_API_URL, data={
                "key": COMMENT_API_KEY,
                "action": "add",
                "service": COMMENT_SERVICE_ID,
                "link": context.user_data["link"],
                "comments": context.user_data["comments"]
            }, timeout=30).json()
        except Exception:
            user_steps[tg] = None
            context.user_data.clear()
            return await update.message.reply_text("❌ API Error", reply_markup=main_menu())

        if "order" in res:
            update_balance(tg, -context.user_data["price"])
            save_order(str(res["order"]), tg, "comments", context.user_data["link"], context.user_data["qty"])
            await update.message.reply_text("✅ Order Placed", reply_markup=main_menu())
        else:
            await update.message.reply_text("❌ Failed", reply_markup=main_menu())

        user_steps[tg] = None
        context.user_data.clear()
        return

    if text == "📦 Orders":
        with DB_LOCK:
            conn = db()
