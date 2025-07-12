# matcher.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
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

# ───────── main command ─────────
async def match_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT role, approved, lat, lon FROM users WHERE telegram_id=?", (uid,))
    me = cur.fetchone()
    if not me:
        await update.message.reply_text("❌ Register first with /register.")
        return
    role, approved, my_lat, my_lon = me
    if role != "woman":
        await update.message.reply_text("🙅 Only Sugar Women can browse matches.")
        return
    if not approved:
        await update.message.reply_text("⏳ Profile pending admin approval.")
        return

    cur.execute("""
      SELECT telegram_id, username, name, age, bio, photo_file_id,
             phone_number, lat, lon
      FROM users
      WHERE role='customer' AND approved=1 AND lat IS NOT NULL AND lon IS NOT NULL
    """)
    cands = cur.fetchall()
    nearby = []
    for c in cands:
        _, _, _, _, _, _, _, lat, lon = c
        if haversine(my_lat, my_lon, lat, lon) <= MATCH_RADIUS_KM:
            nearby.append(c)

    if not nearby:
        await update.message.reply_text("😔 No Sugar Customers within 50 km.")
        return

    context.user_data["matches"] = nearby
    await send_next(update, context)

# ───────── pager helpers ─────────
async def send_next(update: Update | int, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("matches"):
        await context.bot.send_message(chat_id=update.effective_user.id, text="✅ End of list.")
        return
    cid, username, name, age, bio, photo, phone, lat, lon = context.user_data["matches"].pop(0)
    dist = "nearby"
    if context.user_data.get("my_lat"):
        dist_km = haversine(context.user_data["my_lat"], context.user_data["my_lon"], lat, lon)
        dist = f"~{round(dist_km)} km"

    kb = []
    if username:
        kb.append([InlineKeyboardButton("💌 Message", url=f"https://t.me/{username}")])
    elif phone:
        kb.append([InlineKeyboardButton(phone, callback_data="no_action")])
    if context.user_data["matches"]:
        kb.append([InlineKeyboardButton("Next ➡️", callback_data="next_match")])

    await context.bot.send_photo(
        chat_id=update.effective_user.id,
        photo=photo,
        caption=f"*{name}*, {age} y/o ({dist})\n{bio}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb) if kb else None
    )

async def next_match_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await send_next(update, context)

def get_match_handlers():
    return [
        CommandHandler("match", match_cmd),
        CallbackQueryHandler(next_match_cb, pattern="^next_match$"),
    ]
