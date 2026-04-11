import requests
import razorpay
import sqlite3

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton
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

# ================= DB =================
conn = sqlite3.connect("smm.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    balance REAL DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT,
    telegram_id INTEGER,
    service TEXT,
    link TEXT,
    qty INTEGER
)
""")

conn.commit()

# ================= STATE =================
user_steps = {}

def menu():
    return ReplyKeyboardMarkup([
        ["👤 Account", "🛒 Services"],
        ["📦 Orders"]
    ], resize_keyboard=True)

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.message.chat_id

    cursor.execute("INSERT OR IGNORE INTO users (telegram_id) VALUES (?)", (tg_id,))
    conn.commit()

    await update.message.reply_text("🔥 SMM BOT READY", reply_markup=menu())

# ================= SERVICES =================
async def services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💬 Comments ₹250/1000", callback_data="comments")]
    ]

    await update.message.reply_text(
        "Select Service:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= CALLBACK =================
async def cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    tg_id = q.message.chat_id

    if q.data == "comments":
        user_steps[tg_id] = "c_link"
        await q.message.reply_text("🔗 Send Post Link:")

# ================= MAIN HANDLER =================
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.message.chat_id
    text = update.message.text
    step = user_steps.get(tg_id)

    cursor.execute("SELECT balance FROM users WHERE telegram_id=?", (tg_id,))
    row = cursor.fetchone()
    balance = row[0] if row else 0

    # ================= MENU =================
    if text == "🛒 Services":
        await services(update, context)

    elif text == "👤 Account":
        await update.message.reply_text(f"💰 Balance: ₹{balance}")

    # ================= STEP 1: LINK =================
    elif step == "c_link":
        context.user_data["link"] = text
        user_steps[tg_id] = "c_text"

        await update.message.reply_text(
            "💬 अब comments भेजो (one per line)\n\n"
            "Example:\nNice video 🔥\nAwesome bro 😎\nGood gameplay 💯"
        )

    # ================= STEP 2: COMMENTS =================
    elif step == "c_text":

        comments = [c.strip() for c in text.split("\n") if c.strip()]
        qty = len(comments)

        if qty < 1:
            await update.message.reply_text("❌ No comments found")
            return

        price = round((qty / 1000) * 250, 2)

        context.user_data["comments"] = comments
        context.user_data["qty"] = qty
        context.user_data["price"] = price

        user_steps[tg_id] = "c_confirm"

        await update.message.reply_text(
            f"📦 ORDER SUMMARY\n\n"
            f"🔗 Link Saved\n"
            f"💬 Comments: {qty}\n"
            f"💰 Rate: ₹250 / 1000\n"
            f"💳 Total: ₹{price}\n\n"
            f"👉 YES / NO confirm करो"
        )

    # ================= STEP 3: CONFIRM =================
    elif step == "c_confirm":

        if text.lower() == "no":
            user_steps[tg_id] = None
            await update.message.reply_text("❌ Order Cancelled")
            return

        if text.lower() != "yes":
            await update.message.reply_text("👉 YES या NO लिखो")
            return

        link = context.user_data.get("link")
        comments = context.user_data.get("comments")
        qty = context.user_data.get("qty")
        price = context.user_data.get("price")

        if not link:
            user_steps[tg_id] = None
            await update.message.reply_text("❌ Link missing")
            return

        if balance < price:
            await update.message.reply_text(
                f"❌ Low Balance\n💰 Need: ₹{price}\n💳 You: ₹{balance}"
            )
            return

        # deduct balance
        cursor.execute(
            "UPDATE users SET balance=balance-? WHERE telegram_id=?",
            (price, tg_id)
        )
        conn.commit()

        # API CALL
        res = requests.post(COMMENT_API_URL, data={
            "key": COMMENT_API_KEY,
            "action": "add",
            "service": COMMENT_SERVICE_ID,
            "link": link,
            "comments": "\n".join(comments)
        }).json()

        order_id = res.get("order", "NA")

        cursor.execute(
            "INSERT INTO orders VALUES (?,?,?,?,?)",
            (order_id, tg_id, "comments", link, qty)
        )
        conn.commit()

        await update.message.reply_text(
            f"✅ ORDER PLACED\n\n"
            f"💬 Comments: {qty}\n"
            f"💰 Paid: ₹{price}\n"
            f"📦 Order ID: {order_id}"
        )

        user_steps[tg_id] = None

    # ================= ORDERS =================
    elif text == "📦 Orders":
        cursor.execute("SELECT * FROM orders WHERE telegram_id=?", (tg_id,))
        rows = cursor.fetchall()

        if not rows:
            await update.message.reply_text("No orders")
            return

        msg = "📦 LAST ORDERS\n\n"
        for r in rows[-5:]:
            msg += f"{r[2]} | {r[4]} | {r[0]}\n"

        await update.message.reply_text(msg)

# ================= RUN =================
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(cb))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

app.run_polling()
