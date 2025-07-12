from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes
from database import get_conn
import math

MATCH_RADIUS_KM = 50

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi  = math.radians(lat2 - lat1)
    d_lamb = math.radians(lon2 - lon1)
    a = math.sin(d_phi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(d_lamb/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

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
    candidates = cur.fetchall()
    nearby = []
    for c in candidates:
        _, _, _, _, _, _, _, lat, lon = c
        dist = haversine(my_lat, my_lon, lat, lon)
        if dist <= MATCH_RADIUS_KM:
            nearby.append((c, dist))

    if not nearby:
        await update.message.reply_text("😔 No Sugar Customers within 50 km.")
        return

    cust, dist = sorted(nearby, key=lambda x: x[1])[0]
    cid, username, name, age, bio, photo_id, phone, _, _ = cust

    if username:
        kb = [[InlineKeyboardButton("💌 Message", url=f"https://t.me/{username}")]]
        contact_line = f"@{username}"
    elif phone:
        kb = []
        contact_line = f"📞 {phone}"
    else:
        kb = []
        contact_line = "No contact available"

    await update.message.reply_photo(
        photo=photo_id,
        caption=(
            f"*{name}*, {age} y/o\n"
            f"📍 ~{round(dist)} km away\n"
            f"{bio}\n\n"
            f"{contact_line}"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb) if kb else None
    )

def get_match_handlers():
    return [CommandHandler("match", match_cmd)]
