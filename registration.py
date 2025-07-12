# registration.py
from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, Update,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from telegram.ext import (
    ConversationHandler, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from config import ADMIN_CHAT_ID, USDT_WALLET, PAYMENT_AMOUNT
from database import get_conn

# Conversation states
ROLE, PHOTO, NAME, AGE, LOCATION, BIO, PAYMENT = range(7)

def get_registration_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("register", start_registration)],
        states={
            ROLE:      [CallbackQueryHandler(role_selected)],
            PHOTO:     [MessageHandler(filters.PHOTO, photo_received)],
            NAME:      [MessageHandler(filters.TEXT & ~filters.COMMAND, name_received)],
            AGE:       [MessageHandler(filters.TEXT & ~filters.COMMAND, age_received)],
            LOCATION:  [MessageHandler(filters.LOCATION, location_received)],
            BIO:       [MessageHandler(filters.TEXT & ~filters.COMMAND, bio_received)],
            PAYMENT:   [MessageHandler(filters.PHOTO | filters.Document.IMAGE, payment_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="REGISTRATION",
        persistent=True,
    )

# ────────────────────────────────────────────
# Step handlers
# ────────────────────────────────────────────
async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[
        InlineKeyboardButton("👩 Sugar Woman", callback_data="woman"),
        InlineKeyboardButton("🎩 Sugar Customer", callback_data="customer"),
    ]]
    await update.message.reply_text(
        "Please choose your role:",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    return ROLE

async def role_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    context.user_data["role"] = q.data
    await q.message.reply_text("Great! Send a clear profile photo:")
    return PHOTO

async def photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["photo_file_id"] = update.message.photo[-1].file_id
    await update.message.reply_text("What's your name?")
    return NAME

async def name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("How old are you?")
    return AGE

async def age_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["age"] = update.message.text.strip()
    keyboard = [[KeyboardButton("📍 Share Location", request_location=True)]]
    await update.message.reply_text(
        "Tap the button to share your current location:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return LOCATION

async def location_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loc = update.message.location
    if not loc:                                        # ⇦ robust guard
        await update.message.reply_text(
            "⚠️ I didn't get a location. Please tap the *📍 Share Location* button.",
            parse_mode="Markdown"
        )
        return LOCATION

    context.user_data["lat"] = loc.latitude
    context.user_data["lon"] = loc.longitude
    await update.message.reply_text(
        "Perfect! Now type a short bio about yourself:",
        reply_markup=ReplyKeyboardRemove()
    )
    return BIO

async def bio_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["bio"] = update.message.text.strip()
    await update.message.reply_text(
        f"💰 Send *${PAYMENT_AMOUNT} USDT* (TRC‑20) to:\n`{USDT_WALLET}`\n\n"
        "Then upload a screenshot as proof.",
        parse_mode="Markdown"
    )
    return PAYMENT

async def payment_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    proof_id = (
        update.message.photo[-1].file_id
        if update.message.photo else update.message.document.file_id
    )
    context.user_data["payment_proof"] = proof_id

    # Save to DB
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""
      INSERT OR REPLACE INTO users
      (telegram_id, role, username, name, age, bio,
       photo_file_id, payment_proof, lat, lon)
      VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (
        update.effective_user.id,
        context.user_data["role"],
        update.effective_user.username,
        context.user_data["name"],
        context.user_data["age"],
        context.user_data["bio"],
        context.user_data["photo_file_id"],
        proof_id,
        context.user_data["lat"],
        context.user_data["lon"],
    ))
    conn.commit()

    # Notify admin
    kb = [[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve_{update.effective_user.id}"),
        InlineKeyboardButton("❌ Reject",  callback_data=f"reject_{update.effective_user.id}")
    ]]
    await context.bot.send_photo(
        chat_id=ADMIN_CHAT_ID,
        photo=context.user_data["photo_file_id"],
        caption=f"New {context.user_data['role']} pending approval:\n"
                f"{context.user_data['name']} ({context.user_data['age']})",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    await update.message.reply_text(
        "✅ Thank you! Your profile is pending admin approval."
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Registration cancelled.")
    return ConversationHandler.END
