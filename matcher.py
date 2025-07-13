from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import get_conn
import math, time

MATCH_RADIUS_KM = 50
DAYS_VALID = 30
SECONDS_VALID = DAYS_VALID * 24 * 3600

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi  = math.radians(lat2 - lat1)
    dlamb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlamb/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

# /match command
async def match_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cur = get_conn().cursor()
    cur.execute("SELECT role, approved, lat, lon, approved_at FROM users WHERE telegram_id=?", (uid,))
    row = cur.fetchone()

    if not row:
        await update.message.reply_text("❌ Please register first with /register.")
        return

    role, approved, my_lat, my_lon, my_approved_at = row
    now = int(time.time())

    if role != "woman":
        await update.message.reply_text("🙅 Only Sugar Women can browse matches.")
        return
    if not approved or not my_approved_at or (now - my_approved_at) > SECONDS_VALID:
        await update.message.reply_text(
            "⏳ Your subscription has expired. Please /register again for another month."
        )
        return
    if my_lat is None or my_lon is None:
        await update.message.reply_text(
            "⚠️ We couldn't find your location. Please /register again."
        )
        return

    # fetch valid customers
    cur.execute("""
      SELECT telegram_id, username, name, age, bio, photo_file_id,
             phone_number, lat, lon, approved_at
      FROM users
      WHERE role='customer' AND approved=1 AND approved_at IS NOT NULL
            AND (? - approved_at) <= ?
            AND lat IS NOT NULL AND lon IS NOT NULL
    """, (now, SECONDS_VALID))
    candidates = cur.fetchall()
    nearby = [
        c for c in candidates
        if haversine(my_lat, my_lon, c[7], c[8]) <= MATCH_RADIUS_KM
    ]

    if not nearby:
        await update.message.reply_text(
            "😔 Sorry, no Sugar Customers are within 50 km right now.\n"
            "We’ll ping you when someone nearby joins! 🍬"
        )
        return

    context.user_data["matches"] = nearby
    context.user_data["my_lat"] = my_lat
    context.user_data["my_lon"] = my_lon
    await send_next(update.effective_message, context)

# send one profile
async def send_next(msg, context):
    if not context.user_data.get("matches"):
        await context.bot.send_message(msg.chat_id, "✅ End of list for now. Check back later!")
        return

    c = context.user_data["matches"].pop(0)
    cid, username, name, age, bio, photo, phone, lat, lon, _ = c
    dist = round(haversine(context.user_data["my_lat"], context.user_data["my_lon"], lat, lon))
    caption = f"*{name}*, {age} y/o (~{dist} km)\n{bio}"

    buttons = [
        [
            InlineKeyboardButton("✅ Accept", callback_data=f"accept_{cid}"),
            InlineKeyboardButton("❌ Skip",   callback_data="skip_match")
        ]
    ]

    await context.bot.send_photo(
        chat_id=msg.chat_id,
        photo=photo,
        caption=caption,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# skip = next
async def skip_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.delete()
    await send_next(update.callback_query.message, context)

# accept = reveal contact & notify customer
async def accept_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, cid = q.data.split("_"); cid = int(cid)

    cur = get_conn().cursor()
    cur.execute("SELECT username, phone_number FROM users WHERE telegram_id=?", (cid,))
    row = cur.fetchone()
    username, phone = row if row else (None, None)

    # Notify customer
    await context.bot.send_message(
        chat_id=cid,
        text=(
            "🍬 Sweet news! A Sugar Woman liked your profile.\n"
            "Keep an eye on your Telegram — she may DM you soon!"
        )
    )

    # Send contact to woman
    if username:
        contact = f"Here is his Telegram link:\nhttps://t.me/{username}"
    elif phone:
        contact = f"Here is his phone number:\n{phone}"
    else:
        contact = "This customer has no public contact info."

    await q.message.edit_reply_markup(reply_markup=None)
    await q.message.reply_text(f"✅ Accepted!\n\n{contact}")

    # load next automatically
    await send_next(q.message, context)

def get_match_handlers():
    return [
        CommandHandler("match", match_cmd),
        CallbackQueryHandler(skip_cb, pattern="^skip_match$"),
        CallbackQueryHandler(accept_cb, pattern="^accept_\\d+$"),
    ]
