import logging
from telegram.ext import Application, CommandHandler, PicklePersistence
from config import BOT_TOKEN, ADMIN_CHAT_ID
from registration import get_registration_conversation
from approval import get_approval_handler
from matcher import get_match_handlers
import database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update, context):
    welcome = (
        "🍬 *Welcome to SUGAR CONNECT!*\n\n"
        "💃 Find Sugar Women | 🎩 Meet Generous Sponsors\n"
        "🔐 100% Private & Discreet\n"
        "💰 Start Your Sweet Connection Today!\n\n"
        "👉 /register to begin!"
    )
    await update.message.reply_text(welcome, parse_mode="Markdown")

async def error_handler(update, context):
    import traceback, html
    err = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    logger.error(err)
    await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"<pre>{html.escape(err)}</pre>", parse_mode="HTML")

def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .persistence(PicklePersistence(filepath="bot_state.pkl"))
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(get_registration_conversation())

    # approval handlers (list)
    for h in get_approval_handler():
        app.add_handler(h)

    # match handlers (list)
    for h in get_match_handlers():
        app.add_handler(h)

    app.add_error_handler(error_handler)
    logger.info("Bot running via long polling…")
    app.run_polling()

if __name__ == "__main__":
    main()
