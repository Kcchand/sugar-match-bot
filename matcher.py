from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import get_conn
import math

MATCH_RADIUS_KM = 50

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi  = math.radians(lat2 - lat1)
    dlamb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlamb/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

async def match_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT role, approved, lat, lon FROM users WHERE telegram_id=?", (uid,))
    row = cur.fetchone()

    if not row:
        await update.message.reply_text("❌ Please register first with /register.")
        return

    role, approved, my_lat, my_lon = row
    if role != "woman":
        await update.message.reply_text("🙅 Only Sugar Women can browse matches.")
        return
    if not approved:
        await update.message.reply_text("⏳ Your profile is still under review.")
        return
    if my_lat is None or my_lon is None:
        await update.message.reply_text(
            "⚠️ We couldn't find your location. Please /register again and ensure "
            "you provide your city and country."
        )
        return

    cur.execute("""
      SELECT telegram_id, username, name, age, bio, photo_file_id,
             phone_number, lat, lon
      FROM users
      WHERE role='customer' AND approved=1 AND lat IS NOT NULL AND lon IS NOT NULL
    """)
    customers = cur.fetchall()
    nearby = [c for c in customers if haversine(my_lat, my_lon, c[7], c[8]) <= MATCH_RADIUS_KM]

    if not nearby:
        await update.message.reply_text(
            "😔 Sorry, no Sugar Customers are within 50 km right now.\n"
            "We'll notify you as soon as someone nearby joins! 🍬"
        )
        return

    context.user_data["matches"] = nearby
    context.user_data["my_lat"] = my_lat
    context.user_data["my_lon"] = my_lon
    await send_next(update.effective_message, context)

async def send_next(msg, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("matches"):
        await context.bot.send_message(msg.chat_id, "✅ You've seen all nearby customers for now.")
        return

    cust = context.user_data["matches"].pop(0)
    cid, username, name, age, bio, photo, phone, lat, lon = cust
    dist = haversine(context.user_data["my_lat"], context.user_data["my_lon"], lat, lon)
    dist_label = f"~{round(dist)} km away"

    buttons = []
    if username:
        buttons.append([InlineKeyboardButton("💌 Message", url=f"https://t.me/{username}")])
    elif phone:
        buttons.append([InlineKeyboardButton(phone, callback_data="no_action")])
    buttons.append([InlineKeyboardButton("✅ Accept", callback_data=f"accept_{cid}")])
    if context.user_data["matches"]:
        buttons.append([InlineKeyboardButton("Next ➡️", callback_data="next_match")])

    await context.bot.send_photo(
        chat_id=msg.chat_id,
        photo=photo,
        caption=f"*{name}*, {age} y/o ({dist_label})\n{bio}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def next_match_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await send_next(update.callback_query.message, context)

async def accept_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    _, cid = q.data.split("_"); cid = int(cid)

    await context.bot.send_message(
        chat_id=cid,
        text=(
            "🍬 Sweet news! A Sugar Woman liked your profile.\n"
            "Watch your Telegram — she might DM you soon!"
        )
    )
    await q.message.reply_text("✅ Customer notified! Feel free to reach out now.")
    await q.message.edit_reply_markup(reply_markup=None)

def get_match_handlers():
    return [
        CommandHandler("match", match_cmd),
        CallbackQueryHandler(next_match_cb, pattern="^next_match$"),
        CallbackQueryHandler(accept_cb, pattern="^accept_\\d+$"),
    ]
