import requests
import razorpay
import sqlite3
import hmac
import hashlib
import os
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import threading

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
    conn.execute("BEGIN IMMEDIATE")
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
    return ReplyKeyboardMarkup([["YES", "NO"]], resize_keyboard=True)

BACK = ReplyKeyboardMarkup([["⬅️ Back"]], resize_keyboard=True)

# ===== BOT =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.message.chat_id
    await update.message.reply_text(f"💰 Balance: ₹{get_balance(tg)}", reply_markup=main_menu())

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.message.chat_id
    text = update.message.text
    step = user_steps.get(tg)

    if text == "⬅️ Back":
        user_steps[tg] = None
        return await update.message.reply_text("Main Menu", reply_markup=main_menu())

    if text == "👤 Account":
        return await update.message.reply_text(f"💰 ₹{get_balance(tg)}")

    # ===== RECHARGE =====
    if text == "💰 Recharge":
        user_steps[tg] = "amount"
        return await update.message.reply_text("Enter amount:", reply_markup=BACK)

    if step == "amount":
        if not text.isdigit():
            return await update.message.reply_text("Enter valid number")

        amt = int(text)

        link = client.payment_link.create({
            "amount": amt * 100,
            "currency": "INR",
            "notes": {"telegram_id": str(tg)}
        })

        user_steps[tg] = None
        return await update.message.reply_text(link['short_url'])

    # ===== SERVICES =====
    if text == "🛒 Services":
        return await update.message.reply_text("Choose:", reply_markup=services_menu())

    # ===== LIKE =====
    if "👍 Likes" in text:
        user_steps[tg] = "l1"
        return await update.message.reply_text("Send link:", reply_markup=BACK)

    if step == "l1":
        context.user_data["link"] = text
        user_steps[tg] = "l2"
        return await update.message.reply_text("Enter quantity (Min 50):")

    if step == "l2":
        if not text.isdigit():
            return await update.message.reply_text("Invalid")

        qty = int(text)
        if qty < 50:
            return await update.message.reply_text("Minimum 50")

        price = (qty / 1000) * 29
        context.user_data["qty"] = qty
        context.user_data["price"] = price

        user_steps[tg] = "l3"
        return await update.message.reply_text(
            f"{qty} Likes = ₹{round(price,2)}\nType YES to confirm",
            reply_markup=confirm_kb()
        )

    if step == "l3":
        if text != "YES":
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

    # ===== ORDERS =====
    if text == "📦 Orders":
        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM orders WHERE telegram_id=?", (tg,))
        rows = cur.fetchall()
        conn.close()

        if not rows:
            return await update.message.reply_text("No orders")

        msg = "Last Orders:\n"
        for r in rows[-5:]:
            msg += f"{r[2]} | {r[4]}\n"

        await update.message.reply_text(msg)

# ===== WEBHOOK =====
app_web = Flask(__name__)

@app_web.route("/webhook", methods=["POST"])
def webhook():
    try:
        body = request.data
        sig = request.headers.get("X-Razorpay-Signature")

        gen = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()

        if not hmac.compare_digest(gen, sig):
            print("INVALID SIGNATURE")
            return {"status": "invalid"}, 400

        data = request.json
        print("WEBHOOK:", data)

        if data.get("event") == "payment.captured":
            payment = data["payload"]["payment"]["entity"]

            pid = payment["id"]
            amt = payment["amount"] / 100

            notes = payment.get("notes", {})
            tg = notes.get("telegram_id")

            if not tg:
                print("NO TG ID")
                return {"status": "no tg"}

            tg = int(tg)

            if payment_exists(pid):
                print("DUPLICATE")
                return {"status": "duplicate"}

            print("ADDING:", tg, amt)

            update_balance(tg, amt)
            save_payment(pid, tg, amt)

            requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                         params={"chat_id": tg, "text": f"✅ ₹{amt} added"})

        return {"status": "ok"}

    except Exception as e:
        print("ERROR:", str(e))
        return {"status": "error"}

# ===== RUN =====
def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    print("BOT STARTED")
    app.run_polling(drop_pending_updates=True)

def run_web():
    print("WEBHOOK STARTED")
    app_web.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    # ✅ FIX: remove old webhook (conflict fix)
    try:
        requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
    except:
        pass

    t = threading.Thread(target=run_web)
    t.daemon = True
    t.start()

    run_bot()
