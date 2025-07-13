from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import TelegramError
from database import get_conn
import math, time

MATCH_RADIUS_KM   = 50
DAYS_VALID        = 30
SECONDS_VALID     = DAYS_VALID * 86400
NOTIFY_COOLDOWN   = 48 * 3600  # 48 hours

def haversine(a_lat, a_lon, b_lat, b_lon):
    R = 6371
    dlat = math.radians(b_lat - a_lat)
    dlon = math.radians(b_lon - a_lon)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(a_lat))*math.cos(math.radians(b_lat))*math.sin(dlon/2)**2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# /match or Browse button
async def match_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = update.effective_message
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
            await msg.reply_text("🙅 Only Sugar Women can use this."); return
        if not approved or now - approved_at > SECONDS_VALID:
            await msg.reply_text("⏳ Subscription expired. Please /register again."); return
        if my_lat is None or my_lon is None:
            await msg.reply_text("⚠️ Location missing. /register again with city, country."); return

        # fetch nearby customers
        cur.execute("""
          SELECT telegram_id, username, name, age, bio, photo_file_id,
                 phone_number, lat, lon, approved_at
          FROM users
          WHERE role='customer' AND approved=1
                AND (? - approved_at) <= ?
                AND lat IS NOT NULL AND lon IS NOT NULL
        """, (now, SECONDS_VALID))
        cands = [c for c in cur.fetchall() if haversine(my_lat,my_lon,c[7],c[8])<=MATCH_RADIUS_KM]

        if not cands:
            await msg.reply_text(
                "😔 No Sugar Customers within 50 km.\nChoose:",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔔 Auto Notify",  callback_data="enable_auto"),
                    InlineKeyboardButton("🔍 Manual Check", callback_data="disable_auto")
                ]])
            )
            return

        context.user_data["matches"] = cands
        context.user_data["my_lat"], context.user_data["my_lon"] = my_lat, my_lon
        await send_next(msg, context)

    except TelegramError:
        await update.effective_message.reply_text("⚠️ Sorry, something went wrong. Please try again later.")
    except Exception as e:
        print("Match Error:", e)

async def send_next(msg, context):
    if not context.user_data.get("matches"):
        await context.bot.send_message(msg.chat_id, "✅ End of list. Check later."); return
    c = context.user_data["matches"].pop(0)
    cid, username, name, age, bio, photo, phone, lat, lon, _ = c
    dist = round(haversine(context.user_data["my_lat"],context.user_data["my_lon"],lat,lon))
    cap = f"*{name}*, {age} y/o (~{dist} km)\n{bio}"
    kb = [[InlineKeyboardButton("✅ Accept",f"accept_{cid}"),
           InlineKeyboardButton("❌ Skip","skip_match")]]
    try:
        await context.bot.send_photo(msg.chat_id, photo, caption=cap, parse_mode="Markdown",
                                     reply_markup=InlineKeyboardMarkup(kb))
    except TelegramError:
        await msg.reply_text("⚠️ Couldn't load profile. Try later.")

async def skip_cb(u,c): await u.callback_query.answer(); await u.callback_query.message.delete(); await send_next(u.callback_query.message,c)

async def accept_cb(update, context):
    try:
        q = update.callback_query; await q.answer()
        cid = int(q.data.split("_")[1])
        cur=get_conn().cursor(); cur.execute("SELECT username,phone_number FROM users WHERE telegram_id=?", (cid,))
        row = cur.fetchone() or (None,None); username, phone=row
        await context.bot.send_message(cid, "🍬 A Sugar Woman liked you!")
        contact = f"https://t.me/{username}" if username else phone or "No contact info."
        await q.message.edit_reply_markup(reply_markup=None)
        await q.message.reply_text(f"✅ Accepted!\n\n{contact}")
        await send_next(q.message, context)
    except TelegramError:
        await update.effective_message.reply_text("⚠️ Sorry, something went wrong while accepting.")

async def auto_mode_cb(update, context):
    enable = update.callback_query.data == "enable_auto"
    user_id = update.effective_user.id
    state = context.application.bot_data.setdefault("auto_notify", {})
    state[user_id] = {"enabled": enable, "last": 0, "notified": set()}
    await update.callback_query.answer("🔔 Auto-on!" if enable else "🔕 Auto-off.")
    await update.callback_query.message.edit_reply_markup(reply_markup=None)

async def stop_notify_cmd(update, context):
    state = context.application.bot_data.setdefault("auto_notify", {})
    state[update.effective_user.id] = {"enabled": False, "last": 0, "notified": set()}
    await update.message.reply_text("🔕 Auto‑notify disabled.")

async def notify_women_if_needed(context, cust_lat, cust_lon, customer_id):
    try:
        cur = get_conn().cursor()
        cur.execute("SELECT username,name,age,bio,photo_file_id,phone_number,lat,lon FROM users WHERE telegram_id=?", (customer_id,))
        d = cur.fetchone();  if not d: return
        username,name,age,bio,photo,phone,lat,lon=d
        cap_tpl = f"*{name}*, {age} y/o (~{{}} km)\n{bio}"
        kb=[[InlineKeyboardButton("✅ Accept",f"accept_{customer_id}"),
             InlineKeyboardButton("❌ Skip","skip_match")]]
        bot_state = context.application.bot_data.setdefault("auto_notify", {})
        now = int(time.time())

        cur.execute("SELECT telegram_id,lat,lon FROM users WHERE role='woman' AND approved=1 AND lat IS NOT NULL AND lon IS NOT NULL")
        for wid,wlat,wlon in cur.fetchall():
            if haversine(cust_lat,cust_lon,wlat,wlon)>MATCH_RADIUS_KM: continue
            st = bot_state.setdefault(wid, {"enabled": False, "last": 0, "notified": set()})
            if not st["enabled"]: continue
            if customer_id in st["notified"] or now-st["last"]<NOTIFY_COOLDOWN: continue
            dist=round(haversine(wlat,wlon,lat,lon))
            try:
                await context.bot.send_photo(wid, photo, caption=cap_tpl.format(dist),
                                             parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                st["last"] = now
                st["notified"].add(customer_id)
            except TelegramError:
                await context.bot.send_message(wid, "⚠️ A new profile is available, but failed to load. Try /match.")
    except Exception as e:
        print("Notify Error:", e)

def get_match_handlers():
    return [
        CommandHandler("match", match_cmd),
        CommandHandler("stopnotify", stop_notify_cmd),
        CallbackQueryHandler(skip_cb,  pattern="^skip_match$"),
        CallbackQueryHandler(accept_cb,pattern="^accept_\\d+$"),
        CallbackQueryHandler(auto_mode_cb, pattern="^enable_auto$|^disable_auto$")
    ]
