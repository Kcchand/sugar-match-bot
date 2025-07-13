from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import get_conn
import math, time

MATCH_RADIUS_KM = 50
DAYS_VALID = 30
SECONDS_VALID = DAYS_VALID * 86400
NOTIFY_COOLDOWN = 48 * 3600  # 48 hours in seconds

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

# ───────────── /match ─────────────
async def match_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    uid = update.effective_user.id
    cur = get_conn().cursor()
    cur.execute("SELECT role, approved, lat, lon, approved_at FROM users WHERE telegram_id=?", (uid,))
    row = cur.fetchone()
    if not row:
        await msg.reply_text("❌ Please register first with /register."); return

    role, approved, my_lat, my_lon, approved_at = row
    now = int(time.time())
    if role != "woman":
        await msg.reply_text("🙅 Only Sugar Women can use this."); return
    if not approved or not approved_at or now - approved_at > SECONDS_VALID:
        await msg.reply_text("⏳ Your access expired. Please /register again."); return
    if my_lat is None or my_lon is None:
        await msg.reply_text("⚠️ Location missing. Please /register again."); return

    cur.execute("""
        SELECT telegram_id, username, name, age, bio, photo_file_id,
               phone_number, lat, lon, approved_at
        FROM users
        WHERE role='customer' AND approved=1 AND (? - approved_at) <= ?
              AND lat IS NOT NULL AND lon IS NOT NULL
    """, (now, SECONDS_VALID))
    candidates = cur.fetchall()
    matches = [c for c in candidates if haversine(my_lat, my_lon, c[7], c[8]) <= MATCH_RADIUS_KM]

    if not matches:
        await msg.reply_text(
            "😔 No Sugar Customers nearby.\nChoose what you want to do:",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔔 Auto Notify", callback_data="enable_auto_notify"),
                    InlineKeyboardButton("🔍 Manual Check", callback_data="disable_auto_notify")
                ]
            ])
        )
        return

    context.user_data["matches"] = matches
    context.user_data["my_lat"] = my_lat
    context.user_data["my_lon"] = my_lon
    await send_next(msg, context)

# ───────────── Send 1 profile ─────────────
async def send_next(msg, context):
    if not context.user_data.get("matches"):
        await context.bot.send_message(msg.chat_id, "✅ End of list. Check later.")
        return

    c = context.user_data["matches"].pop(0)
    cid, username, name, age, bio, photo, phone, lat, lon, _ = c
    dist_km = round(haversine(context.user_data["my_lat"], context.user_data["my_lon"], lat, lon))
    caption = f"*{name}*, {age} y/o (~{dist_km} km)\n{bio}"
    buttons = [[
        InlineKeyboardButton("✅ Accept", callback_data=f"accept_{cid}"),
        InlineKeyboardButton("❌ Skip", callback_data="skip_match")
    ]]
    await context.bot.send_photo(
        chat_id=msg.chat_id,
        photo=photo,
        caption=caption,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ───────────── Accept / Skip ─────────────
async def skip_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.delete()
    await send_next(update.callback_query.message, context)

async def accept_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    _, cid = q.data.split("_"); cid = int(cid)

    cur = get_conn().cursor()
    cur.execute("SELECT username, phone_number FROM users WHERE telegram_id=?", (cid,))
    row = cur.fetchone()
    username, phone = row if row else (None, None)

    await context.bot.send_message(
        chat_id=cid,
        text="🍬 A Sugar Woman liked your profile! She may message you soon."
    )
    contact = f"https://t.me/{username}" if username else phone or "No contact info."
    await q.message.edit_reply_markup(reply_markup=None)
    await q.message.reply_text(f"✅ Accepted!\n\n{contact}")
    await send_next(q.message, context)

# ───────────── Auto / Manual Notify ─────────────
async def auto_notify_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.callback_query.data
    context.user_data["auto_notify"] = (choice == "enable_auto_notify")
    context.user_data["last_notified"] = 0
    context.user_data["notified_customers"] = set()
    await update.callback_query.answer(
        "🔔 Auto-notify enabled!" if choice == "enable_auto_notify" else "🔕 Manual mode set."
    )
    await update.callback_query.message.edit_reply_markup(reply_markup=None)

# ───────────── /stopnotify ─────────────
async def stop_notify_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["auto_notify"] = False
    await update.message.reply_text("🔕 Auto-notify disabled. You can still use /match anytime.")

# ───────────── 🔔 Push Profile If New ─────────────
async def notify_women_if_needed(context, customer_lat, customer_lon, customer_id):
    cur = get_conn().cursor()
    cur.execute("SELECT telegram_id, username, name, age, bio, photo_file_id, phone_number, lat, lon FROM users WHERE telegram_id=?", (customer_id,))
    c = cur.fetchone()
    if not c: return

    cid, username, name, age, bio, photo, phone, lat, lon = c
    caption_template = f"*{name}*, {age} y/o (~{{dist}} km)\n{bio}"
    buttons = [[
        InlineKeyboardButton("✅ Accept", callback_data=f"accept_{cid}"),
        InlineKeyboardButton("❌ Skip", callback_data="skip_match")
    ]]

    cur.execute("SELECT telegram_id, lat, lon FROM users WHERE role='woman' AND approved=1 AND lat IS NOT NULL AND lon IS NOT NULL")
    women = cur.fetchall()
    now = int(time.time())

    for wid, wlat, wlon in women:
        if haversine(customer_lat, customer_lon, wlat, wlon) <= MATCH_RADIUS_KM:
            data = context.application.user_data.setdefault(wid, {})
            if not data.get("auto_notify"): continue

            # Respect cooldown
            last = data.get("last_notified", 0)
            notified = data.setdefault("notified_customers", set())
            if customer_id in notified: continue
            if now - last < NOTIFY_COOLDOWN: continue

            # Send profile
            try:
                dist = round(haversine(wlat, wlon, lat, lon))
                await context.bot.send_photo(
                    chat_id=wid,
                    photo=photo,
                    caption=caption_template.format(dist=dist),
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
                # Update state
                data["last_notified"] = now
                data["notified_customers"].add(customer_id)
            except Exception as e:
                print(f"❌ Notify failed: {e}")

# ───────────── Register handlers ─────────────
def get_match_handlers():
    return [
        CommandHandler("match", match_cmd),
        CommandHandler("stopnotify", stop_notify_cmd),
        CallbackQueryHandler(skip_cb,  pattern="^skip_match$"),
        CallbackQueryHandler(accept_cb,pattern="^accept_\\d+$"),
        CallbackQueryHandler(auto_notify_cb, pattern="^enable_auto_notify$|^disable_auto_notify$")
    ]
