import requests
import razorpay
import sqlite3
import hmac
import hashlib
import os
import asyncio

from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ===== CONFIG =====
BOT_TOKEN = "8748370733:AAFckHBCRlh5jfS0XfBQuOf4iPDAjWZqri4"
ADMIN_ID = 8451049817

LIKE_API_KEY = "7d01eb30166546130c171b26eecee191"
LIKE_API_URL = "https://tntsmm.in/api/v2"
LIKE_SERVICE_ID = "7283"
LIKE_QUANTITY = 51

COMMENT_API_KEY = "7d01eb30166546130c171b26eecee191"
COMMENT_API_URL = "https://tntsmm.in/api/v2"
COMMENT_SERVICE_ID = "7406"
FIXED_COMMENTS = """Crazy stunts 🔥
Insane jump 😱
Nice crash 💥
Epic bro
Too good 😎
Full action
Kya stunt tha
Mast video
Next level
Fire gameplay 🔥
Smooth landing
Hard bro 💪
Crazy jump
OMG 😱
Full power
Nice try
Cool stunt
Badiya hai"""

RAZORPAY_KEY = "rzp_live_Sc7lXEOJ2ZWjPL"
RAZORPAY_SECRET = "KxRu3ssMBcNLTQ7LxMY0jZIQ"
WEBHOOK_SECRET = "ayush@123"

APP_URL = "https://smm-production-494a.up.railway.app"

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


# ===== KEYBOARDS =====
user_steps = {}

def service_choice_kb():
    return ReplyKeyboardMarkup(
        [["👍 Like (51)", "💬 Comments (18)"]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def orders_balance_kb():
    return ReplyKeyboardMarkup(
        [["📦 My Orders", "💰 My Balance"]],
        resize_keyboard=True
    )


# ===== HANDLERS =====
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.message.chat_id
    get_balance(tg)
    await update.message.reply_text(
        "🔥 *SMM Panel Bot*\n\n📌 Post ka link bhejo, main service choose karne dunga!",
        parse_mode="Markdown",
        reply_markup=orders_balance_kb()
    )

# ===== ADMIN COMMANDS =====
async def all_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.chat_id): return
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT telegram_id, balance FROM users ORDER BY balance DESC")
    rows = cur.fetchall()
    conn.close()
    if not rows:
        return await update.message.reply_text("No users found")
    msg = "👥 All Users:\n\n"
    for r in rows:
        msg += f"🆔 {r[0]} | 💰 ₹{round(r[1],2)}\n"
    for i in range(0, len(msg), 4000):
        await update.message.reply_text(msg[i:i+4000])

async def cut_balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.chat_id): return
    try:
        tg = int(context.args[0]); amt = float(context.args[1])
        update_balance(tg, -amt)
        await update.message.reply_text(f"❌ ₹{amt} deducted from {tg}")
    except:
        await update.message.reply_text("Usage: /cutbalance USER_ID AMOUNT")

async def check_balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.chat_id): return
    try:
        tg = int(context.args[0])
        await update.message.reply_text(f"🆔 {tg} Balance: ₹{get_balance(tg)}")
    except:
        await update.message.reply_text("Usage: /balance USER_ID")

async def add_balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.chat_id): return
    try:
        tg = int(context.args[0]); amt = float(context.args[1])
        update_balance(tg, amt)
        await update.message.reply_text(f"✅ Added ₹{amt} to {tg}")
    except:
        await update.message.reply_text("Usage: /addbalance USER_ID AMOUNT")

async def news_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.chat_id): return
    if not context.args:
        return await update.message.reply_text("Usage: /news your message")
    msg_text = " ".join(context.args)
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT telegram_id FROM users")
    users = cur.fetchall()
    conn.close()
    success = failed = 0
    for u in users:
        try:
            await context.bot.send_message(chat_id=u[0], text=f"📢 {msg_text}")
            success += 1
            await asyncio.sleep(0.05)
        except:
            failed += 1
    await update.message.reply_text(f"📊 Broadcast Done\n✅ {success} Sent\n❌ {failed} Failed")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.chat_id): return
    try:
        tg = int(context.args[0])
        conn = db(); cur = conn.cursor()
        cur.execute("UPDATE users SET banned=1 WHERE telegram_id=?", (tg,))
        conn.commit(); conn.close()
        await update.message.reply_text(f"🚫 User {tg} banned")
    except:
        await update.message.reply_text("Usage: /ban USER_ID")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.chat_id): return
    try:
        tg = int(context.args[0])
        conn = db(); cur = conn.cursor()
        cur.execute("UPDATE users SET banned=0 WHERE telegram_id=?", (tg,))
        conn.commit(); conn.close()
        await update.message.reply_text(f"✅ User {tg} unbanned")
    except:
        await update.message.reply_text("Usage: /unban USER_ID")

async def profit_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.chat_id): return
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT SUM(amount) FROM payments")
    total_recharge = cur.fetchone()[0] or 0
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM orders")
    total_orders = cur.fetchone()[0]
    cur.execute("SELECT service, quantity FROM orders")
    orders = cur.fetchall()
    conn.close()
    total_cost = total_revenue = 0
    for service, qty in orders:
        if service == "likes":
            total_revenue += (qty / 1000) * 400
            total_cost += (qty / 1000) * 200
        elif service == "comments":
            total_revenue += (qty / 1000) * 400
            total_cost += (qty / 1000) * 250
    profit = total_revenue - total_cost
    await update.message.reply_text(
        f"📈 Profit Dashboard\n\n"
        f"💰 Total Recharge: ₹{round(total_recharge,2)}\n"
        f"💵 Revenue: ₹{round(total_revenue,2)}\n"
        f"📉 Cost: ₹{round(total_cost,2)}\n"
        f"💸 Profit: ₹{round(profit,2)}\n\n"
        f"👤 Users: {total_users}\n📦 Orders: {total_orders}"
    )


# ===== MAIN MESSAGE HANDLER =====
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.message.chat_id
    text = update.message.text.strip()

    # BAN CHECK
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT banned FROM users WHERE telegram_id=?", (tg,))
    r = cur.fetchone(); conn.close()
    if r and r[0] == 1:
        return await update.message.reply_text("🚫 You are banned")

    step = user_steps.get(tg)

    # ── My Balance ──
    if text == "💰 My Balance":
        return await update.message.reply_text(f"💰 Balance: ₹{get_balance(tg)}", reply_markup=orders_balance_kb())

    # ── My Orders ──
    if text == "📦 My Orders":
        conn = db(); cur = conn.cursor()
        cur.execute("SELECT order_id, service, quantity FROM orders WHERE telegram_id=? ORDER BY rowid DESC LIMIT 5", (tg,))
        rows = cur.fetchall(); conn.close()
        if not rows:
            return await update.message.reply_text("No orders found", reply_markup=orders_balance_kb())
        msg = "📦 Last 5 Orders:\n\n"
        for o in rows:
            status = check_order_status(o[0], LIKE_API_URL, LIKE_API_KEY)
            st = status.get("status", "Unknown") if status else "Unknown"
            msg += f"🆔 {o[0]}\n📌 {o[1]} | Qty: {o[2]} | Status: {st}\n\n"
        return await update.message.reply_text(msg, reply_markup=orders_balance_kb())

    # ── User sends a link → show Like/Comment choice ──
    if "http" in text and step is None:
        context.user_data["link"] = text
        user_steps[tg] = "choose_service"
        return await update.message.reply_text(
            "✅ Link mila!\n\nAb service choose karo:",
            reply_markup=service_choice_kb()
        )

    # ── Service chosen ──
    if step == "choose_service":
        link = context.user_data.get("link")
        if not link:
            user_steps[tg] = None
            return await update.message.reply_text("❌ Pehle link bhejo", reply_markup=orders_balance_kb())

        if text == "👍 Like (51)":
            price = (LIKE_QUANTITY / 1000) * 400
            bal = get_balance(tg)
            user_steps[tg] = None

            if bal < price:
                return await update.message.reply_text(
                    f"⚠️ Low balance!\n💰 Balance: ₹{bal}\n💵 Required: ₹{price}\n\nAdmin se balance add karwao: @ayushpatelh",
                    reply_markup=orders_balance_kb()
                )

            res = requests.post(LIKE_API_URL, data={
                "key": LIKE_API_KEY,
                "action": "add",
                "service": LIKE_SERVICE_ID,
                "link": link,
                "quantity": LIKE_QUANTITY
            }).json()

            if "order" in res:
                update_balance(tg, -price)
                save_order(res["order"], tg, "likes", link, LIKE_QUANTITY)
                requests.get(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    params={"chat_id": ADMIN_ID, "text": f"👍 New LIKE order\nUser: {tg}\nLink: {link}\nOrder ID: {res['order']}"}
                )
                await update.message.reply_text(
                    f"✅ Like order placed!\n\n🆔 Order ID: {res['order']}\n📌 Qty: {LIKE_QUANTITY}\n💰 Charged: ₹{price}\n💰 Remaining: ₹{round(bal-price,2)}",
                    reply_markup=orders_balance_kb()
                )
            else:
                await update.message.reply_text(f"❌ Order failed: {res}", reply_markup=orders_balance_kb())
            context.user_data.clear()
            return

        elif text == "💬 Comments (18)":
            comments_list = [c.strip() for c in FIXED_COMMENTS.strip().split("\n") if c.strip()]
            qty = len(comments_list)
            price = (qty / 1000) * 400
            bal = get_balance(tg)
            user_steps[tg] = None

            if bal < price:
                return await update.message.reply_text(
                    f"⚠️ Low balance!\n💰 Balance: ₹{bal}\n💵 Required: ₹{price}\n\nAdmin se balance add karwao: @ayushpatelh",
                    reply_markup=orders_balance_kb()
                )

            res = requests.post(COMMENT_API_URL, data={
                "key": COMMENT_API_KEY,
                "action": "add",
                "service": COMMENT_SERVICE_ID,
                "link": link,
                "comments": "\n".join(comments_list)
            }).json()

            if "order" in res:
                update_balance(tg, -price)
                save_order(res["order"], tg, "comments", link, qty)
                requests.get(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    params={"chat_id": ADMIN_ID, "text": f"💬 New COMMENT order\nUser: {tg}\nLink: {link}\nOrder ID: {res['order']}"}
                )
                await update.message.reply_text(
                    f"✅ Comment order placed!\n\n🆔 Order ID: {res['order']}\n📌 Comments: {qty}\n💰 Charged: ₹{price}\n💰 Remaining: ₹{round(bal-price,2)}",
                    reply_markup=orders_balance_kb()
                )
            else:
                await update.message.reply_text(f"❌ Order failed: {res}", reply_markup=orders_balance_kb())
            context.user_data.clear()
            return

        else:
            return await update.message.reply_text("👇 Like ya Comment choose karo:", reply_markup=service_choice_kb())

    # ── Unknown ──
    await update.message.reply_text("📌 Post ka link bhejo:", reply_markup=orders_balance_kb())


# ===== REGISTER HANDLERS =====
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("balance", check_balance_cmd))
telegram_app.add_handler(CommandHandler("addbalance", add_balance_cmd))
telegram_app.add_handler(CommandHandler("cutbalance", cut_balance_cmd))
telegram_app.add_handler(CommandHandler("user", all_users))
telegram_app.add_handler(CommandHandler("news", news_broadcast))
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

@app.route("/set_webhook")
def set_webhook():
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
    r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={APP_URL}/{BOT_TOKEN}")
    return r.json()

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
            params={"chat_id": tg, "text": f"✅ ₹{amt} added to your balance!"}
        )
        requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            params={"chat_id": ADMIN_ID, "text": f"New payment ₹{amt} from {tg}"}
        )
    return {"status": "ok"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
