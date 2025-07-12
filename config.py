import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
USDT_WALLET = os.getenv("USDT_WALLET", "")
PAYMENT_AMOUNT = float(os.getenv("PAYMENT_AMOUNT", "20"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing.")
