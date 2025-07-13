from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import get_conn
import math, time

MATCH_RADIUS_KM = 50
DAYS_VALID      = 30
SECONDS_VALID   = DAYS_VALID * 86400

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

# ───────────────── /match (or Browse button) ─────────────────
async def match_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message          # works for both Message & CallbackQuery
    uid = update.effective_user.id
    cur = get_conn().cursor()
    cur.execute("SELECT role, approved, lat, lon, approved_at FROM users WHERE telegram_id=?", (uid,))
    row = cur.fetchone()

    if not row:
        await msg.reply_text("❌ Please register first with /register.")
        return

    role, approved, my_lat, my_lon, approved_at = row
    now = int(time.time())

    if role != "woman":
        await msg.reply_text("🙅 Only Sugar Women can use this.")
        return
    if not approved or not approved_at or now - approved_at > SECONDS_VALID:
        await msg.reply_text("⏳ Your monthly access expired. Please /register again.")
        return
    if my_lat is None or my_lon is None:
        await msg.reply_text("⚠️ Location missing. Please /register again with city, country.")
        return

    # fetch valid nearby customers
    cur.execute("""
      SELECT telegram_id, username, name, age, bio, photo_file_id,
             phone_number, lat, lon, approved_at
      FROM users
      WHERE role='customer' AND approved=1 AND approved_at IS NOT NULL
            AND (? - approved_at) <= ?
            AND lat IS NOT NULL AND lon IS NOT NULL
    """, (now, SECONDS_VALID))
    cands = cur.fetchall()
    nearby = [
        c for c in cands
        if haversine(my_lat, my_lon, c[7], c[8]) <= MATCH_RADIUS_KM
    ]

    if not nearby:
        await msg.reply_text(
            "😔 No Sugar Customers within 50 km right now.\n"
            "Choose an option:",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔔 Auto Notify", callback_data="enable_auto_notify"),
                    InlineKeyboardButton("🔍 Manual Check", callback_data="disable_auto_notify")
                ]
            ])
        )
        return

    context.user_data["matches"] = nearby
    context.user_data["my_lat"]  = my_lat
    context.user_data["my_lon"]  = my_lon
    await send_next(msg, context)

# ───────────────── send one profile ─────────────────
async def send_next(msg, context):
    if not context.user_data.get("matches"):
        await context.bot.send_message(msg.chat_id, "✅ End of list for now.")
        return

    c = context.user_data["matches"].pop(0)
    cid, username, name, age, bio, photo, phone, lat, lon, _ = c
    dist = round(haversine(context.user_data["my_lat"], context.user_data["my_lon"], lat, lon))
    caption = f"*{name}*, {age} y/o (~{dist} km)\n{bio}"

    buttons = [[
        InlineKeyboardButton("✅ Accept", callback_data=f"accept_{cid}"),
        InlineKeyboardButton("❌ Skip",   callback_data="skip_match")
    ]]

    await context.bot.send_photo(
        chat_id=msg.chat_id,
        photo=photo,
        caption=caption,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# Skip = next
async def skip_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.delete()
    await send_next(update.callback_query.message, context)

# Accept = reveal contact & notify customer
async def accept_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    _, cid = q.data.split("_"); cid = int(cid)

    cur = get_conn().cursor()
    cur.execute("SELECT username, phone_number FROM users WHERE telegram_id=?", (cid,))
    username, phone = cur.fetchone() if cur.fetchone() else (None, None)

    await context.bot.send_message(
        chat_id=cid,
        text="🍬 A Sugar Woman liked your profile! She may DM you soon."
    )

    contact = f"https://t.me/{username}" if username else phone or "No contact info."
    await q.message.edit_reply_markup(reply_markup=None)
    await q.message.reply_text(f"✅ Accepted!\n\n{contact}")
    await send_next(q.message, context)

# Auto/Manual
async def auto_notify_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.callback_query.data
    context.user_data["auto_notify"] = (choice == "enable_auto_notify")
    await update.callback_query.answer(
        "Auto‑notify enabled!" if choice == "enable_auto_notify" else "Manual mode selected."
    )
    await update.callback_query.message.edit_reply_markup(reply_markup=None)

# Notify women (called from approval.py)
async def notify_women_if_needed(context, customer_lat, customer_lon, customer_id):
    cur = get_conn().cursor()
    cur.execute("""
      SELECT telegram_id, lat, lon
      FROM users
      WHERE role='woman' AND approved=1 AND lat IS NOT NULL AND lon IS NOT NULL
    """)
    for wid, wlat, wlon in cur.fetchall():
        if haversine(customer_lat, customer_lon, wlat, wlon) <= MATCH_RADIUS_KM:
            if context.application.user_data.get(wid, {}).get("auto_notify"):
                try:
                    dummy_update = Update(update_id=0, callback_query=None)
                    dummy_update.effective_chat = type("obj", (), {"id": wid})
                    dummy_update.effective_user = type("obj", (), {"id": wid})
                    dummy_update.effective_message = type("obj", (), {"chat_id": wid})
                    await match_cmd(dummy_update, context)
                except Exception:
                    pass

def get_match_handlers():
    return [
        CommandHandler("match", match_cmd),
        CallbackQueryHandler(skip_cb,  pattern="^skip_match$"),
        CallbackQueryHandler(accept_cb,pattern="^accept_\\d+$"),
        CallbackQueryHandler(auto_notify_cb, pattern="^enable_auto_notify$|^disable_auto_notify$")
    ]
