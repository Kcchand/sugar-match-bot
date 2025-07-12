# bot.py
import logging
from telegram.ext import Application, CommandHandler, PicklePersistence
from config import BOT_TOKEN
from registration import get_registration_conversation
from approval import get_approval_handler
from matcher import get_match_handlers
import database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update, context):
    welcome = (
        "🍬 *Welcome to SUGAR CONNECT!*

"
        "💃 _Find Sugar Women_  |  🎩 _Meet Generous Sponsors_
"
        "🔐 100% Private & Discreet
"
        "💰 Start Your Sweet Connection Today!

"
        "👉 Tap /register to begin your journey!"
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
    app.add_handler(get_registration_conversation())
    app.add_handler(get_approval_handler())
    for h in get_match_handlers():
        app.add_handler(h)

    logger.info("Bot running via long polling…")
    app.run_polling()

if __name__ == "__main__":
    main()
