import os, logging, html, sys, asyncio, traceback
from telegram import Update
from telegram.ext import (
    Application, PicklePersistence,
    CommandHandler, ContextTypes
)
from telegram.error import TelegramError, Conflict

from config import BOT_TOKEN, ADMIN_CHAT_ID
from registration import get_registration_conversation
from approval import get_approval_handler
from matcher import get_match_handlers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- /start ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🍬 *Welcome to SUGAR CONNECT!*\n\n"
        "💃 Find Sugar Women | 🎩 Meet Generous Sponsors\n"
        "🔐 100% Private & Discreet\n"
        "💰 Monthly membership: $50\n\n"
        "👉 Use /register to begin.",
        parse_mode="Markdown"
    )

# ---------- global error handler ----------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    # Log full traceback
    tb = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    logger.error(tb)

    # Try to send friendly message to user
    if update and getattr(update, "effective_message", None):
        try:
            await update.effective_message.reply_text(
                "⚠️ Something went wrong. Please try again shortly."
            )
        except TelegramError:
            pass

    # Optional: notify admin
    try:
        await context.bot.send_message(
            ADMIN_CHAT_ID,
            f"⚠️ <b>Bot error</b>:\n<pre>{html.escape(str(context.error))}</pre>",
            parse_mode="HTML"
        )
    except TelegramError:
        pass

    # If polling conflict (already running), shut down
    if isinstance(context.error, Conflict):
        await asyncio.sleep(1)
        sys.exit("❌ Another bot instance is already running. This one will exit.")

# ---------- main ----------
def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .persistence(PicklePersistence(filepath="bot_state.pkl"))
        .build()
    )

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(get_registration_conversation())
    for h in get_approval_handler(): app.add_handler(h)
    for h in get_match_handlers():  app.add_handler(h)

    app.add_error_handler(error_handler)

    logger.info("🚀 Bot is running (long polling)…")
    app.run_polling()

if __name__ == "__main__":
    main()
