from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, Update,
    ReplyKeyboardRemove
)
from telegram.ext import (
    ConversationHandler, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from config import ADMIN_CHAT_ID, USDT_WALLET, PAYMENT_AMOUNT
from database import get_conn
from utils import geocode_address

ROLE, PHOTO, NAME, AGE, LOCATION_TEXT, BIO, PAYMENT = range(7)

def get_registration_conversation():
    return ConversationHandler(
        entry_points=[CommandHandler("register", start_registration)],
        states={
            ROLE:      [CallbackQueryHandler(role_selected)],
            PHOTO:     [MessageHandler(filters.PHOTO, photo_received)],
            NAME:      [MessageHandler(filters.TEXT & ~filters.COMMAND, name_received)],
            AGE:       [MessageHandler(filters.TEXT & ~filters.COMMAND, age_received)],
            LOCATION_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, location_received)],
            BIO:       [MessageHandler(filters.TEXT & ~filters.COMMAND, bio_received)],
            PAYMENT:   [MessageHandler(filters.PHOTO | filters.Document.IMAGE, payment_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="REGISTRATION",
        persistent=True,
    )

async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        InlineKeyboardButton("👩 Sugar Woman", callback_data="woman"),
        InlineKeyboardButton("🎩 Sugar Customer", callback_data="customer"),
    ]]
    await update.message.reply_text(
        "Please choose your role:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ROLE

async def role_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["role"] = query.data
    await query.message.reply_text("Please send a clear profile photo.")
    return PHOTO

async def photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["photo_file_id"] = update.message.photo[-1].file_id
    await update.message.reply_text("What is your name?")
    return NAME

async def name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("How old are you?")
    return AGE

async def age_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["age"] = update.message.text.strip()
    await update.message.reply_text(
        "📍 What's your city and country?\n\n_Example: Kathmandu, Nepal_",
        parse_mode="Markdown"
    )
    return LOCATION_TEXT

async def location_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address = update.message.text.strip()
    lat, lon = await geocode_address(address)

    if lat is None:
        await update.message.reply_text("⚠️ Couldn't find that location. Please try again with just city and country.")
        return LOCATION_TEXT

    context.user_data["location_text"] = address
    context.user_data["lat"] = lat
    context.user_data["lon"] = lon

    await update.message.reply_text("Great! Now type a short bio about yourself:", reply_markup=ReplyKeyboardRemove())
    return BIO

async def bio_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["bio"] = update.message.text.strip()
    await update.message.reply_text(
        f"💰 Send *${PAYMENT_AMOUNT} USDT* (TRC-20) to:\n`{USDT_WALLET}`\n\n"
        "Then upload a screenshot as proof.",
        parse_mode="Markdown"
    )
    return PAYMENT

async def payment_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_id = (
        update.message.photo[-1].file_id
        if update.message.photo else update.message.document.file_id
    )
    context.user_data["payment_proof"] = file_id

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO users
        (telegram_id, role, username, name, age, bio,
         photo_file_id, payment_proof, location_text, lat, lon)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        update.effective_user.id,
        context.user_data["role"],
        update.effective_user.username,
        context.user_data["name"],
        context.user_data["age"],
        context.user_data["bio"],
        context.user_data["photo_file_id"],
        file_id,
        context.user_data["location_text"],
        context.user_data["lat"],
        context.user_data["lon"],
    ))
    conn.commit()

    keyboard = [[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve_{update.effective_user.id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject_{update.effective_user.id}")
    ]]
    await context.bot.send_photo(
        chat_id=ADMIN_CHAT_ID,
        photo=context.user_data["photo_file_id"],
        caption=(
            f"New {context.user_data['role']} pending approval:\n"
            f"{context.user_data['name']} ({context.user_data['age']})\n"
            f"{context.user_data['bio']}\n"
            f"Location: {context.user_data['location_text']}"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text("✅ Your profile has been submitted and is pending admin approval.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Registration cancelled.")
    return ConversationHandler.END
