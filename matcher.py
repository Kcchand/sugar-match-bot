# matcher.py
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    CommandHandler, CallbackQueryHandler, ContextTypes
)
from database import get_conn
import math

MATCH_RADIUS_KM = 50

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_phi  = math.radians(lat2 - lat1)
    d_lamb = math.radians(lon2 - lon1)
    a = math.sin(d_phi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(d_lamb/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

# ───────── main /match command ─────────
async def match_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT role, approved, lat, lon FROM users WHERE telegram_id=?", (uid,))
    me = cur.fetchone()
    if not me:
        await update.message.reply_text("❌ You need to register first with /register.")
        return
    role, approved, my_lat, my_lon = me
    if role != "woman":
        await update.message.reply_text("🙅 Only Sugar Women can browse matches.")
        return
    if not approved:
        await update.message.reply_text("⏳ Your profile is still under review.")
        return

    # Fetch nearby customers
    cur.execute("""
      SELECT telegram_id, username, name, age, bio, photo_file_id,
             phone_number, lat, lon
      FROM users
      WHERE role='customer' AND approved=1 AND lat IS NOT NULL AND lon IS NOT NULL
    """)
    candidates = cur.fetchall()
    nearby = []
    for c in candidates:
        _, _, _, _, _, _, _, lat, lon = c
        if haversine(my_lat, my_lon, lat, lon) <= MATCH_RADIUS_KM:
            nearby.append(c)

    if not nearby:
        await update.message.reply_text(
            "😔 Sorry, no Sugar Customers are within 50 km right now.\n"
            "Don’t worry — the moment someone nearby joins, we’ll let you know! 🍬"
        )
        return

    # Store matches for pagination
    context.user_data["matches"] = nearby
    context.user_data["my_lat"] = my_lat
    context.user_data["my_lon"] = my_lon
    await send_next_match(update.effective_message, context)

# ───────── send one profile ─────────
async def send_next_match(msg, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("matches"):
        await context.bot.send_message(
            chat_id=msg.chat_id,
            text="✅ You’ve seen all available customers nearby for now."
        )
        return

    cust = context.user_data["matches"].pop(0)
    cid, username, name, age, bio, photo, phone, lat, lon = cust

    dist_km = haversine(
        context.user_data["my_lat"], context.user_data["my_lon"], lat, lon
    )
    dist_label = f"~{round(dist_km)} km away"

    buttons = []

    # 1. Contact button
    if username:
        buttons.append([InlineKeyboardButton("💌 Message", url=f"https://t.me/{username}")])
    elif phone:
        buttons.append([InlineKeyboardButton(phone, callback_data="no_action")])

    # 2. Accept button (notifies customer)
    buttons.append([
        InlineKeyboardButton("✅ Accept", callback_data=f"accept_{cid}")
    ])

    # 3. Next button
    if context.user_data["matches"]:
        buttons.append([InlineKeyboardButton("Next ➡️", callback_data="next_match")])

    await context.bot.send_photo(
        chat_id=msg.chat_id,
        photo=photo,
        caption=(
            f"*{name}*, {age} y/o\n"
            f"{dist_label}\n"
            f"{bio}"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ───────── callback handlers ─────────
async def next_match_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await send_next_match(update.callback_query.message, context)

async def accept_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, cid = q.data.split("_")
    cid = int(cid)

    # notify customer
    await context.bot.send_message(
        chat_id=cid,
        text="🍬 Great news! A Sugar Woman liked your profile.\n"
             "Keep an eye on your Telegram — she might DM you soon!"
    )

    # confirm to woman
    await q.edit_message_reply_markup(reply_markup=None)
    await q.message.reply_text("✅ Customer notified! Feel free to contact him now.")

def get_match_handlers():
    return [
        CommandHandler("match", match_cmd),
        CallbackQueryHandler(next_match_cb, pattern="^next_match$"),
        CallbackQueryHandler(accept_cb, pattern="^accept_\\d+$"),
    ]
