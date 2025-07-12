# matcher.py
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CommandHandler, ContextTypes
from database import get_conn
import math

MATCH_RADIUS_KM = 50

def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

async def match_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = get_conn(); cur = conn.cursor()

    # Get current user's info
    cur.execute("SELECT role, approved, lat, lon FROM users WHERE telegram_id=?", (user_id,))
    row = cur.fetchone()

    if not row:
        await update.message.reply_text("❌ You are not registered yet.")
        return

    role, approved, user_lat, user_lon = row
    if not approved:
        await update.message.reply_text("⏳ Your profile is still pending approval.")
        return

    if role != "woman":
        await update.message.reply_text("🙅 Only Sugar Women can browse matches.")
        return

    if not user_lat or not user_lon:
        await update.message.reply_text("⚠️ Your location is missing. Please re-register.")
        return

    # Get all approved customers
    cur.execute("""
        SELECT telegram_id, name, age, bio, photo_file_id, lat, lon
        FROM users
        WHERE role='customer' AND approved=1 AND lat IS NOT NULL AND lon IS NOT NULL
    """)
    customers = cur.fetchall()

    matches = []
    for cust in customers:
        _, name, age, bio, photo_id, lat, lon = cust
        dist = haversine(user_lat, user_lon, lat, lon)
        if dist <= MATCH_RADIUS_KM:
            matches.append((cust, dist))

    if not matches:
        await update.message.reply_text("😔 No Sugar Customers found within 50 km of your location.")
        return

    # Show closest match
    cust, dist = sorted(matches, key=lambda x: x[1])[0]
    cid, name, age, bio, photo_id, _, _ = cust

    kb = [[
        InlineKeyboardButton("💌 Accept", url=f"https://t.me/{cid}"),
    ]]

    await update.message.reply_photo(
        photo=photo_id,
        caption=f"*{name}*, {age} y/o\n📍 ~{round(dist)} km away\n\n_{bio}_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

def get_match_handlers():
    return [CommandHandler("match", match_cmd)]
