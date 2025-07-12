# registration.py
from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardRemove
)
from telegram.ext import (
    ConversationHandler, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from config import ADMIN_CHAT_ID, USDT_WALLET, PAYMENT_AMOUNT
from database import get_conn
from utils import geocode_address, dial_prefix_from_address

ROLE, PHOTO, NAME, AGE, LOCATION_TEXT, BIO, PHONE, PAYMENT = range(8)

# ───────── Conversation definition ─────────
def get_registration_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("register", start_registration)],
        states={
            ROLE:           [CallbackQueryHandler(role_selected)],
            PHOTO:          [MessageHandler(filters.PHOTO, photo_received)],
            NAME:           [MessageHandler(filters.TEXT & ~filters.COMMAND, name_received)],
            AGE:            [MessageHandler(filters.TEXT & ~filters.COMMAND, age_received)],
            LOCATION_TEXT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, location_received)],
            BIO:            [MessageHandler(filters.TEXT & ~filters.COMMAND, bio_received)],
            PHONE:          [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_received)],
            PAYMENT:        [MessageHandler(filters.PHOTO | filters.Document.IMAGE, payment_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="REGISTRATION",
        persistent=True,
    )

# ───────── Step handlers ─────────
async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[
        InlineKeyboardButton("👩 Sugar Woman",   callback_data="woman"),
        InlineKeyboardButton("🎩 Sugar Customer", callback_data="customer"),
    ]]
    await update.message.reply_text("Choose your role:", reply_markup=InlineKeyboardMarkup(kb))
    return ROLE

async def role_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    context.user_data["role"] = q.data
    await q.message.reply_text("Please send a clear profile photo.")
    return PHOTO

async def photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["photo_file_id"] = update.message.photo[-1].file_id
    await update.message.reply_text("Your name?")
    return NAME

async def name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("Your age?")
    return AGE

async def age_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["age"] = update.message.text.strip()
    await update.message.reply_text(
        "📍 What's your city and country?\n\n_Example: city, country_",
        parse_mode="Markdown"
    )
    return LOCATION_TEXT

async def location_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address = update.message.text.strip()
    lat, lon = await geocode_address(address)
    if lat is None:
        await update.message.reply_text("⚠️ Couldn't find that place. Try again (city, country).")
        return LOCATION_TEXT

    context.user_data.update({
        "location_text": address,
        "lat": lat,
        "lon": lon,
    })
    await update.message.reply_text("Write a short bio about yourself:")
    return BIO

async def bio_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["bio"] = update.message.text.strip()

    if context.user_data["role"] == "customer":
        await update.message.reply_text("📞 Phone number (digits only, no spaces):")
        return PHONE

    return await ask_payment(update, context)

async def phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    prefix = dial_prefix_from_address(context.user_data["location_text"])
    if raw.startswith("+"):
        final_phone = raw
    elif prefix:
        final_phone = f"{prefix}{raw.lstrip('0')}"
    else:
        await update.message.reply_text("⚠️ Include country code (e.g. +9779876...).")
        return PHONE

    context.user_data["phone_number"] = final_phone
    return await ask_payment(update, context)

async def ask_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"💰 Send *${PAYMENT_AMOUNT} USDT* (TRC‑20) to:\n`{USDT_WALLET}`\n\n"
        "Then upload a screenshot.",
        parse_mode="Markdown"
    )
    return PAYMENT

async def payment_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    proof_id = (
        update.message.photo[-1].file_id
        if update.message.photo else update.message.document.file_id
    )
    context.user_data["payment_proof"] = proof_id

    phone = context.user_data.get("phone_number")
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""
    INSERT OR REPLACE INTO users
      (telegram_id, role, username, name, age, bio,
       phone_number, photo_file_id, payment_proof,
       location_text, lat, lon)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        update.effective_user.id,
        context.user_data["role"],
        update.effective_user.username,
        context.user_data["name"],
        context.user_data["age"],
        context.user_data["bio"],
        phone,
        context.user_data["photo_file_id"],
        proof_id,
        context.user_data["location_text"],
        context.user_data["lat"],
        context.user_data["lon"],
    ))
    conn.commit()

    kb = [[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve_{update.effective_user.id}"),
        InlineKeyboardButton("❌ Reject",  callback_data=f"reject_{update.effective_user.id}")
    ]]
    await context.bot.send_photo(
        chat_id=ADMIN_CHAT_ID,
        photo=context.user_data["photo_file_id"],
        caption=(
            f"New {context.user_data['role']} pending approval:\n"
            f"{context.user_data['name']} ({context.user_data['age']})\n"
            f"{context.user_data['bio']}\n"
            f"Location: {context.user_data['location_text']}\n"
            f"Phone: {phone or '—'}"
        ),
        reply_markup=InlineKeyboardMarkup(kb)
    )
    await update.message.reply_text("✅ Submitted! Awaiting admin approval.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Registration cancelled.")
    return ConversationHandler.END
