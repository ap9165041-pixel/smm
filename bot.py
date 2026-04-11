import requests
import razorpay
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import threading
import asyncio

# ===== CONFIG =====
BOT_TOKEN = "8748370733:AAHmioo1yYD4GcozjnJVVsN8niakHDzmcnE"
API_KEY = "7d01eb30166546130c171b26eecee191"
API_URL = "https://tntsmm.in/api/v2"

RAZORPAY_KEY = "rzp_live_Sc7lXEOJ2ZWjPL"
RAZORPAY_SECRET = "KxRu3ssMBcNLTQ7LxMY0jZIQ"

client = razorpay.Client(auth=(RAZORPAY_KEY, RAZORPAY_SECRET))

users = {}

# ===== START COMMAND =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.chat_id

    if uid not in users:
        users[uid] = {"balance": 0}

    keyboard = [
        ["💰 Balance", "🔄 Recharge"],
        ["👍 YouTube Likes"]
    ]

    await update.message.reply_text(
        "🚀 Welcome to SMM Bot\n\nSelect option:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# ===== HANDLE BUTTONS =====
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.chat_id
    text = update.message.text

    # ensure user exists
    if uid not in users:
        users[uid] = {"balance": 0}

    # 💰 BALANCE
    if text == "💰 Balance":
        await update.message.reply_text(f"💰 Balance: ₹{users[uid]['balance']}")

    # 🔄 RECHARGE START
    elif text == "🔄 Recharge":
        users[uid]["step"] = "amount"
        await update.message.reply_text("💰 Enter amount to recharge:")

    # 💵 AMOUNT INPUT
    # 💵 AMOUNT INPUT
    elif users[uid].get("step") == "amount":

        # validation
        if not text.strip().isdigit():
            await update.message.reply_text("❌ Enter numbers only")
            return

        amount = int(text.strip())

        if amount < 10:
            await update.message.reply_text("❌ Minimum ₹10 recharge")
            return

        try:
            payment_link = client.payment_link.create({
                "amount": amount * 100,
                "currency": "INR",
                "description": "Wallet Recharge",
                "notify": {
                    "sms": True
                }
            })

            users[uid]["order_id"] = payment_link["id"]
            users[uid]["step"] = None

            pay_link = payment_link["short_url"]

            await update.message.reply_text(
                f"💳 Pay ₹{amount} here:\n{pay_link}"
            )

        except Exception as e:
            print("ERROR:", e)
            await update.message.reply_text("❌ Payment link error, try again")

    # 👍 YOUTUBE LIKES
    elif text == "👍 YouTube Likes":
        users[uid]["action"] = "yt"
        await update.message.reply_text("🔗 Send YouTube Video Link")

    # 🎯 ORDER
    elif "youtube" in text or "youtu.be" in text:
        if users[uid]["balance"] < 30:
            await update.message.reply_text("❌ Low Balance")
            return

        users[uid]["balance"] -= 30

        data = {
            "key": API_KEY,
            "action": "add",
            "service": "3062",
            "link": text,
            "quantity": 100
        }

        res = requests.post(API_URL, data=data).json()

        if "order" in res:
            await update.message.reply_text(f"✅ Order Success\n🆔 ID: {res['order']}")
        else:
            await update.message.reply_text(f"❌ Error: {res}") 
# ===== FLASK WEBHOOK =====
app_web = Flask(__name__)

@app_web.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    if data.get("event") == "payment.captured":
        payment = data["payload"]["payment"]["entity"]

        order_id = payment["order_id"]
        amount = payment["amount"] / 100

        for uid in users:
            if users[uid].get("order_id") == order_id:
                users[uid]["balance"] += amount
                users[uid]["order_id"] = None
                print(f"₹{amount} added to {uid}")

    return {"status": "ok"}

# ===== TELEGRAM BOT =====
def start_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    print("🤖 Bot Started...")
    app.run_polling()
# ===== WEB SERVER =====
def start_web():
    print("🌐 Webhook Started...")
    app_web.run(host="0.0.0.0", port=5000)

# ===== MAIN =====
if __name__ == "__main__":
    threading.Thread(target=start_web).start()
    start_bot()