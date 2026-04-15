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

# ===== ADMIN CHECK =====
def is_admin(user_id):
    return user_id == ADMIN_ID

# ===== BALANCE =====
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

# ===== ORDER STATUS =====
def check_order_status(order_id, api_url, api_key):
    try:
        res = requests.post(api_url, data={
            "key": api_key,
            "action": "status",
            "order": order_id
        }).json()
        return res
    except:
        return None

# ===== UI =====
user_steps = {}

def main_menu():
    return ReplyKeyboardMarkup(
        [
            ["👤 Account", "💰 Recharge"],
            ["📦 Orders", "🛒 Services"],
            ["🎧 Support"]
        ],
        resize_keyboard=True
    )

def services_menu():
    return ReplyKeyboardMarkup(
        [
            ["👍 NON Drop Likes (₹39/1000)", "💬 Comments (₹250/1000)"],
            ["⬅️ Back"]
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

    msg = f"""
🔥 Welcome to Premium SMM Panel

🚀 Fast Delivery
💎 Cheapest Rates
⚡ Instant Service

━━━━━━━━━━━━━━━
💰 Balance: ₹{bal}
━━━━━━━━━━━━━━━
"""
    await update.message.reply_text(msg, reply_markup=main_menu())

# ===== ADMIN COMMANDS =====

async def check_balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.chat_id):
        return

    try:
        tg = int(context.args[0])
        bal = get_balance(tg)
        await update.message.reply_text(f"User {tg} Balance: ₹{bal}")
    except:
        await update.message.reply_text("Usage: /balance USER_ID")
        
async def add_balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.chat_id):
        return
    try:
        tg = int(context.args[0])
        amt = float(context.args[1])
        update_balance(tg, amt)
        await update.message.reply_text(f"✅ Added ₹{amt} to {tg}")
    except:
        await update.message.reply_text("Usage: /addbalance USER_ID AMOUNT")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.chat_id):
        return
    try:
        tg = int(context.args[0])
        conn = db()
        cur = conn.cursor()
        cur.execute("UPDATE users SET banned=1 WHERE telegram_id=?", (tg,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"🚫 User {tg} banned")
    except:
        await update.message.reply_text("Usage: /ban USER_ID")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.chat_id):
        return
    try:
        tg = int(context.args[0])
        conn = db()
        cur = conn.cursor()
        cur.execute("UPDATE users SET banned=0 WHERE telegram_id=?", (tg,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ User {tg} unbanned")
    except:
        await update.message.reply_text("Usage: /unban USER_ID")

# ===== PROFIT DASHBOARD =====
async def profit_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.chat_id):
        return

    conn = db()
    cur = conn.cursor()

    # 💰 Total Recharge
    cur.execute("SELECT SUM(amount) FROM payments")
    total_recharge = cur.fetchone()[0] or 0

    # 👤 Users
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]

    # 📦 Orders
    cur.execute("SELECT COUNT(*) FROM orders")
    total_orders = cur.fetchone()[0]

    # 📊 Orders Data
    cur.execute("SELECT service, quantity FROM orders")
    orders = cur.fetchall()

    total_cost = 0
    total_revenue = 0

    for service, qty in orders:
        # SELL PRICE (your price)
        if service == "likes":
            sell = (qty / 1000) * 39
            cost = (qty / 1000) * 13   # ✅ REAL COST

        elif service == "comments":
            sell = (qty / 1000) * 250
            cost = (qty / 1000) * 120  # ✅ REAL COST

        total_revenue += sell
        total_cost += cost

    profit = total_revenue - total_cost

    conn.close()

    msg = f"""
📈 Profit Dashboard

💰 Total Recharge: ₹{round(total_recharge,2)}
💵 Revenue: ₹{round(total_revenue,2)}
📉 Cost: ₹{round(total_cost,2)}
💸 Profit: ₹{round(profit,2)}

━━━━━━━━━━━━━━━
👤 Users: {total_users}
📦 Orders: {total_orders}
"""
    await update.message.reply_text(msg)

# ===== MAIN HANDLER =====
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.message.chat_id
    text = update.message.text
    step = user_steps.get(tg)

    # BAN CHECK
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT banned FROM users WHERE telegram_id=?", (tg,))
    r = cur.fetchone()
    conn.close()

    if r and r[0] == 1:
        return await update.message.reply_text("🚫 You are banned")

    if text == "⬅️ Back":
        user_steps[tg] = None
        return await update.message.reply_text("Main Menu", reply_markup=main_menu())

    if text == "👤 Account":
        user = update.message.from_user
        return await update.message.reply_text(
            f"🆔 {tg}\n👤 {user.first_name}\n💰 ₹{get_balance(tg)}" )

    if text == "🎧 Support":
        return await update.message.reply_text("Contact Admin: @ayushpatelh")

    # ===== ORDERS =====
    if text == "📦 Orders":
        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT order_id, service, quantity FROM orders WHERE telegram_id=? ORDER BY rowid DESC LIMIT 5", (tg,))
        rows = cur.fetchall()
        conn.close()

        if not rows:
            return await update.message.reply_text("No orders found")

        msg = "📦 Orders:\n\n"
        for o in rows:
            status = check_order_status(o[0], LIKE_API_URL, LIKE_API_KEY)
            st = status.get("status", "Unknown") if status else "Unknown"
            msg += f"{o[0]} | {o[1]} | {o[2]} | {st}\n"

        return await update.message.reply_text(msg)

    # ===== RECHARGE =====
    if text == "💰 Recharge":
        user_steps[tg] = "amount"
        return await update.message.reply_text("Enter amount:", reply_markup=BACK)

    if step == "amount":
        if not text.isdigit():
            return await update.message.reply_text("Invalid amount")

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

      # ===== LIKES =====
    if text.startswith("👍 NON Drop Likes"):
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
        if qty <= 0:
            return await update.message.reply_text("Invalid quantity")

        price = (qty / 1000) * 39

        context.user_data["qty"] = qty
        context.user_data["price"] = price

        user_steps[tg] = "l3"
        return await update.message.reply_text(f"{qty} Likes = ₹{price}", reply_markup=confirm_kb())

    if step == "l3":
        if text != "✅ Confirm":
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

            requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                params={"chat_id": ADMIN_ID, "text": f"New LIKE order from {tg}"}
            )

            await update.message.reply_text("Order placed", reply_markup=main_menu())

        user_steps[tg] = None
        context.user_data.clear()

    # ===== COMMENTS =====
    if text.startswith("💬 Comments"):
        user_steps[tg] = "c1"
        return await update.message.reply_text("Send link:", reply_markup=BACK)

    # Step 1: Link
    if step == "c1":
        if "http" not in text:
            return await update.message.reply_text("Invalid link")

        context.user_data["link"] = text
        user_steps[tg] = "c2"
        return await update.message.reply_text("Send comments (one per line):")

    # Step 2: Comments
    if step == "c2":
        comments_list = text.strip().split("\n")

        comments_list = [c.strip() for c in comments_list if c.strip()]

        if len(comments_list) == 0:
            return await update.message.reply_text("No valid comments")

        if len(comments_list) > 1000:
            return await update.message.reply_text("Max 1000 comments allowed")

        qty = len(comments_list)
        price = (qty / 1000) * 250

        context.user_data["comments"] = "\n".join(comments_list)
        context.user_data["qty"] = qty
        context.user_data["price"] = price

        user_steps[tg] = "c3"
        return await update.message.reply_text(
            f"{qty} Comments = ₹{price}",
            reply_markup=confirm_kb()
        )

    # Step 3: Confirm
    if step == "c3":
        if text != "✅ Confirm":
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
            save_order(
                res["order"],
                tg,
                "comments",
                context.user_data["link"],
                context.user_data["qty"]
            )

            requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                params={"chat_id": ADMIN_ID, "text": f"New COMMENT order from {tg}"}
            )

            await update.message.reply_text(
                f"✅ Order placed\nID: {res['order']}",
                reply_markup=main_menu()
            )
        else:
            await update.message.reply_text("❌ Order failed")

        user_steps[tg] = None
        context.user_data.clear() 
        
    
# ===== HANDLERS =====
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("balance", check_balance_cmd))
telegram_app.add_handler(CommandHandler("addbalance", add_balance_cmd))
telegram_app.add_handler(CommandHandler("ban", ban_user))
telegram_app.add_handler(CommandHandler("unban", unban_user))
telegram_app.add_handler(CommandHandler("profit", profit_dashboard))
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

        # USER MSG
        requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            params={"chat_id": tg, "text": f"₹{amt} added"}
        )

        # ADMIN MSG
        requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            params={"chat_id": ADMIN_ID, "text": f"New payment ₹{amt} from {tg}"}
        )

    return {"status": "ok"}

# ===== START =====
if __name__ == "__main__":
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={APP_URL}/{BOT_TOKEN}")

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port) 
