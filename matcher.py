# matcher.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import get_conn
import math

MATCH_RADIUS_KM = 50

def haversine(lat1, lon1, lat2, lon2):
    """Great‑circle distance in km."""
    R = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_phi  = math.radians(lat2 - lat1)
    d_lamb = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lamb / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# ───────────────────────────────────────────
# /match command
# ───────────────────────────────────────────
async def match_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cur = get_conn().cursor()
    cur.execute("SELECT role, approved, lat, lon FROM users WHERE telegram_id=?", (uid,))
    row = cur.fetchone()

    # Early‑exit checks with explicit replies
    if not row:
        await update.message.reply_text("❌ Please register first with /register.")
        return

    role, approved, my_lat, my_lon = row
    if role != "woman":
        await update.message.reply_text("🙅 Only Sugar Women can browse matches.")
        return
    if not approved:
        await update.message.reply_text("⏳ Your profile is still being reviewed.")
        return
    if my_lat is None or my_lon is None:
        await update.message.reply_text(
            "⚠️ We don't have your location. Please /register again with a valid city & country."
        )
        return

    # Fetch all approved customers and filter by distance
    cur.execute("""
      SELECT telegram_id, username, name, age, bio, photo_file_id,
             phone_number, lat, lon
      FROM users
      WHERE role='customer' AND approved=1 AND lat IS NOT NULL AND lon IS NOT NULL
    """)
    candidates = cur.fetchall()
    nearby = [
        c for c in candidates
        if haversine(my_lat, my_lon, c[7], c[8]) <= MATCH_RADIUS_KM
    ]

    if not nearby:
        await update.message.reply_text(
            "😔 Sorry, no Sugar Customers are within 50 km right now.\n"
            "We’ll let you know as soon as someone nearby joins! 🍬"
        )
        return

    # Store nearby list for paging
    context.user_data["matches"] = nearby
    context.user_data["my_lat"] = my_lat
    context.user_data["my_lon"] = my_lon
    await send_next(update.effective_message, context)

# ───────────────────────────────────────────
# Helper to send the next profile
# ───────────────────────────────────────────
async def send_next(msg, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("matches"):
        await context.bot.send_message(msg.chat_id, "✅ You've seen all nearby customers for now.")
        return

    cust = context.user_data["matches"].pop(0)
    cid, username, name, age, bio, photo, phone, lat, lon = cust
    dist = haversine(context.user_data["my_lat"], context.user_data["my_lon"], lat, lon)
    dist_label = f"~{round(dist)} km away"

    # Buttons: Accept + (optional) Next
    buttons = [[InlineKeyboardButton("✅ Accept", callback_data=f"accept_{cid}")]]
    if context.user_data["matches"]:
        buttons.append([InlineKeyboardButton("Next ➡️", callback_data="next_match")])

    await context.bot.send_photo(
        chat_id=msg.chat_id,
        photo=photo,
        caption=f"*{name}*, {age} y/o ({dist_label})\n{bio}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ───────────────────────────────────────────
# Callback for Next ➡️
# ───────────────────────────────────────────
async def next_match_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await send_next(update.callback_query.message, context)

# ───────────────────────────────────────────
# Callback for Accept ✅
# ───────────────────────────────────────────
async def accept_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, cid = q.data.split("_")
    cid = int(cid)

    cur = get_conn().cursor()
    cur.execute("SELECT username, phone_number FROM users WHERE telegram_id=?", (cid,))
    row = cur.fetchone()
    username, phone = row if row else (None, None)

    # Notify the customer
    await context.bot.send_message(
        chat_id=cid,
        text=(
            "🍬 Sweet news! A Sugar Woman liked your profile.\n"
            "Keep an eye on your Telegram — she may DM you soon."
        )
    )

    # Show contact info to the woman
    if username:
        contact = f"Here is his Telegram link:\nhttps://t.me/{username}"
    elif phone:
        contact = f"Here is his phone number:\n{phone}"
    else:
        contact = "This customer has no public contact info."

    await q.message.reply_text(f"✅ Accepted!\n\n{contact}")
    await q.message.edit_reply_markup(reply_markup=None)

# ───────────────────────────────────────────
# Export handler list
# ───────────────────────────────────────────
def get_match_handlers():
    return [
        CommandHandler("match", match_cmd),
        CallbackQueryHandler(next_match_cb, pattern="^next_match$"),
        CallbackQueryHandler(accept_cb, pattern="^accept_\\d+$"),
    ]
