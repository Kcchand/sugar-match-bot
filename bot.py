import os, logging
from telegram.ext import Application, PicklePersistence, CommandHandler
from telegram.error import Conflict, TelegramError
from config import BOT_TOKEN, ADMIN_CHAT_ID
from registration import get_registration_conversation
from approval import get_approval_handler
from matcher import get_match_handlers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- simple /start ----------
async def start(update, context):
    await update.message.reply_text(
        "🍬 *Welcome to SUGAR CONNECT!*\n\n"
        "💃 Find Sugar Women | 🎩 Meet Generous Sponsors\n"
        "🔐 100% Private & Discreet\n"
        f"💰 Monthly membership: ${int(os.getenv('PAYMENT_AMOUNT', '50'))}\n\n"
        "👉 Use /register to begin.",
        parse_mode="Markdown"
    )

# ---------- global error handler ----------
async def error_handler(update, context):
    import traceback, html, sys, asyncio
    err_txt = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    logger.error(err_txt)

    # user-facing friendly message
    if update and getattr(update, "effective_message", None):
        try:
            await update.effective_message.reply_text(
                "⚠️ Sorry, something went wrong. Please try again."
            )
        except TelegramError:
            pass

    # admin short log
    try:
        await context.bot.send_message(
            ADMIN_CHAT_ID,
            text=f"<pre>{html.escape(str(context.error))}</pre>",
            parse_mode="HTML"
        )
    except TelegramError:
        pass

    # auto-exit on polling conflict
    if isinstance(context.error, Conflict):
        await asyncio.sleep(1)
        sys.exit("Another instance is already polling")

# ---------- main ----------
def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .persistence(PicklePersistence(filepath="bot_state.pkl"))
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(get_registration_conversation())

    # approval (list) + match (list)
    for h in get_approval_handler(): app.add_handler(h)
    for h in get_match_handlers():  app.add_handler(h)

    app.add_error_handler(error_handler)
    logger.info("Bot running via long polling…")
    app.run_polling()

if __name__ == "__main__":
    main()
