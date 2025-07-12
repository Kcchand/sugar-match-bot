# bot.py
import logging
from telegram.ext import Application, CommandHandler, PicklePersistence

from config import BOT_TOKEN
from registration import get_registration_conversation
from approval import get_approval_handler
from matcher import get_match_handlers
import database  # creates tables

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update, context):
    welcome = (
        "🍬 *Welcome to SUGAR CONNECT!*\n\n"
        "💃 Find Sugar Women | 🎩 Meet Generous Sponsors\n"
        "🔐 100% Private & Discreet\n"
        "💰 Start Your Sweet Connection Today!\n\n"
        "👉 Click /register to begin!"
    )
    await update.message.reply_text(welcome, parse_mode="Markdown")

def main():
    persistence = PicklePersistence(filepath="bot_state.pkl")
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .persistence(persistence)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(get_registration_conversation())   # registration flow
    app.add_handler(get_approval_handler())            # admin approve / reject
    for h in get_match_handlers():                     # (stub) matching command
        app.add_handler(h)

    logger.info("Bot running via long‑polling …")
    app.run_polling()                                  # ← no start_webhook

if __name__ == "__main__":
    main()
