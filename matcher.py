# matcher.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import get_conn
import math, time

MATCH_RADIUS_KM = 50
DAYS_VALID = 30
SECONDS_VALID = DAYS_VALID * 86400

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# /match
async def match_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cur = get_conn().cursor()
    cur.execute("SELECT role, approved, lat, lon, approved_at FROM users WHERE telegram_id=?", (uid,))
    row = cur.fetchone()

    if not row:
        await update.message.reply_text("❌ Please register first with /register.")
        return

    role, approved, my_lat, my_lon, approved_at = row
    now = int(time.time())

    if role != "woman":
        await update.message.reply_text("🙅 Only Sugar Women can use /match.")
        return
    if not approved or not approved_at or (now - approved_at > SECONDS_VALID):
        await update.message.reply_text("⏳ Your access expired. Please /register again for next month.")
        return
    if my_lat is None or my_lon is None:
        await update.message.reply_text("⚠️ Location missing. Please /register again with city, country.")
        return

    # get valid nearby customers
    cur.execute("""
      SELECT telegram_id, username, name, age, bio, photo_file_id,
             phone_number, lat, lon, approved_at
      FROM users
      WHERE role='customer' AND approved=1 AND approved_at IS NOT NULL
            AND (? - approved_at) <= ? AND lat IS NOT NULL AND lon IS NOT NULL
    """, (now, SECONDS_VALID))
    candidates = cur.fetchall()

    matches = [
        c for c in candidates
        if haversine(my_lat, my_lon, c[7], c[8]) <= MATCH_RADIUS_KM
    ]

    if not matches:
        # No matches — offer auto/manual notification
        context.user_data["auto_notify"] = False  # default = manual
        await update.message.reply_text(
            "😔 No Sugar Customers are available within 50 km right now.\n\n"
            "Would you like to be notified automatically when someone appears nearby?",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔔 Auto Notify Me", callback_data="enable_auto_notify"),
                    InlineKeyboardButton("🔍 Manual Check", callback_data="disable_auto_notify")
                ]
            ])
        )
        return

    context.user_data["matches"] = matches
    context.user_data["my_lat"] = my_lat
    context.user_data["my_lon"] = my_lon
    await send_next(update.effective_message, context)

# Show customer profile
async def send_next(msg, context):
    if not context.user_data.get("matches"):
        await context.bot.send_message(msg.chat_id, "✅ You've seen all nearby profiles. Check again later!")
        return

    cust = context.user_data["matches"].pop(0)
    cid, username, name, age, bio, photo, phone, lat, lon, _ = cust
    dist_km = round(haversine(context.user_data["my_lat"], context.user_data["my_lon"], lat, lon))

    caption = f"*{name}*, {age} y/o (~{dist_km} km away)\n{bio}"
    buttons = [
        [
            InlineKeyboardButton("✅ Accept", callback_data=f"accept_{cid}"),
            InlineKeyboardButton("❌ Skip", callback_data="skip_match")
        ]
    ]

    await context.bot.send_photo(
        chat_id=msg.chat_id,
        photo=photo,
        caption=caption,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# Skip = load next profile
async def skip_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.delete()
    await send_next(update.callback_query.message, context)

# Accept = reveal contact
async def accept_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, cid = q.data.split("_"); cid = int(cid)

    cur = get_conn().cursor()
    cur.execute("SELECT username, phone_number FROM users WHERE telegram_id=?", (cid,))
    row = cur.fetchone()
    username, phone = row if row else (None, None)

    await context.bot.send_message(
        chat_id=cid,
        text="🍬 A Sugar Woman liked your profile! Watch your Telegram — she may DM you soon!"
    )

    if username:
        contact = f"Here’s his Telegram:\nhttps://t.me/{username}"
    elif phone:
        contact = f"Here’s his phone number:\n{phone}"
    else:
        contact = "This customer has no contact info."

    await q.message.edit_reply_markup(reply_markup=None)
    await q.message.reply_text(f"✅ Accepted!\n\n{contact}")
    await send_next(q.message, context)

# Auto/manual notification toggle
async def auto_notify_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.callback_query.data
    if choice == "enable_auto_notify":
        context.user_data["auto_notify"] = True
        await update.callback_query.message.edit_text("🔔 Auto-notify enabled! We'll alert you when new matches are nearby.")
    else:
        context.user_data["auto_notify"] = False
        await update.callback_query.message.edit_text("✅ Manual mode selected. You can run /match anytime.")

# Externally trigger this when a customer is approved
# matcher.py

async def notify_women_if_needed(context, customer_lat, customer_lon, customer_id=None):
    cur = get_conn().cursor()
    cur.execute("""
      SELECT telegram_id, lat, lon
      FROM users
      WHERE role='woman' AND approved=1 AND lat IS NOT NULL AND lon IS NOT NULL
    """)
    women = cur.fetchall()

    for wid, wlat, wlon in women:
        dist = haversine(customer_lat, customer_lon, wlat, wlon)
        if dist <= MATCH_RADIUS_KM:
            data = context.application.user_data.setdefault(wid, {})
            if data.get("auto_notify"):
                try:
                    # Reuse match logic to send profile directly
                    cur.execute("""
                        SELECT telegram_id, username, name, age, bio, photo_file_id,
                               phone_number, lat, lon, approved_at
                        FROM users WHERE telegram_id=? LIMIT 1
                    """, (customer_id,))
                    cust = cur.fetchone()
                    if not cust: continue

                    cid, username, name, age, bio, photo, phone, lat, lon, _ = cust
                    dist_km = round(haversine(wlat, wlon, lat, lon))
                    caption = f"*{name}*, {age} y/o (~{dist_km} km)\n{bio}"

                    buttons = [[
                        InlineKeyboardButton("✅ Accept", callback_data=f"accept_{cid}"),
                        InlineKeyboardButton("❌ Skip", callback_data="skip_match")
                    ]]

                    await context.bot.send_photo(
                        chat_id=wid,
                        photo=photo,
                        caption=caption,
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(buttons)
                    )
                except Exception as e:
                    print(f"❌ Notify error: {e}")


def get_match_handlers():
    return [
        CommandHandler("match", match_cmd),
        CallbackQueryHandler(skip_cb, pattern="^skip_match$"),
        CallbackQueryHandler(accept_cb, pattern="^accept_\\d+$"),
        CallbackQueryHandler(auto_notify_cb, pattern="^enable_auto_notify$|^disable_auto_notify$")
    ]
