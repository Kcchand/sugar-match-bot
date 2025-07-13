from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import get_conn
import math, time

MATCH_RADIUS_KM   = 50
DAYS_VALID        = 30
SECONDS_VALID     = DAYS_VALID * 86400
NOTIFY_COOLDOWN   = 48 * 3600  # 48 h

def haversine(a_lat, a_lon, b_lat, b_lon):
    R = 6371
    dlat = math.radians(b_lat - a_lat)
    dlon = math.radians(b_lon - a_lon)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(a_lat))*math.cos(math.radians(b_lat))*math.sin(dlon/2)**2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# ───────── /match or Browse button ─────────
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
    if not approved or now - approved_at > SECONDS_VALID:
        await msg.reply_text("⏳ Subscription expired. Please /register again."); return
    if my_lat is None or my_lon is None:
        await msg.reply_text("⚠️ Location missing. /register again with city, country."); return

    # nearby customers (still valid)
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
            "😔 No Sugar Customers within 50 km.\nChoose what to do:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔔 Auto Notify",  callback_data="enable_auto"),
                InlineKeyboardButton("🔍 Manual Check", callback_data="disable_auto")
            ]])
        )
        return

    context.user_data["matches"] = cands
    context.user_data["my_lat"]  = my_lat
    context.user_data["my_lon"]  = my_lon
    await send_next(msg, context)

# ───────── send one profile ─────────
async def send_next(msg, context):
    if not context.user_data.get("matches"):
        await context.bot.send_message(msg.chat_id,"✅ End of list. Come back later!")
        return
    cid, username, name, age, bio, photo, phone, lat, lon, _ = context.user_data["matches"].pop(0)
    dist = round(haversine(context.user_data["my_lat"],context.user_data["my_lon"],lat,lon))
    caption = f"*{name}*, {age} y/o (~{dist} km)\n{bio}"
    kb=[[InlineKeyboardButton("✅ Accept",f"accept_{cid}"),
         InlineKeyboardButton("❌ Skip","skip_match")]]
    await context.bot.send_photo(
        chat_id=msg.chat_id, photo=photo,
        caption=caption, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# Skip/Accept
async def skip_cb(u,c): await u.callback_query.answer(); await u.callback_query.message.delete(); await send_next(u.callback_query.message,c)

async def accept_cb(update, context):
    q=update.callback_query;await q.answer()
    cid=int(q.data.split("_")[1])
    cur=get_conn().cursor();cur.execute("SELECT username,phone_number FROM users WHERE telegram_id=?", (cid,))
    row=cur.fetchone() or (None,None);username,phone=row
    await context.bot.send_message(chat_id=cid,text="🍬 A Sugar Woman liked you!")
    contact=f"https://t.me/{username}" if username else phone or "No contact info."
    await q.message.edit_reply_markup(reply_markup=None)
    await q.message.reply_text(f"✅ Accepted!\n\n{contact}")
    await send_next(q.message,context)

# Auto / Manual
async def auto_mode_cb(update, context):
    enable = update.callback_query.data == "enable_auto"
    bot_state = context.application.bot_data.setdefault("auto_notify", {})  # writable dict
    bot_state[update.effective_user.id] = {
        "enabled": enable,
        "last": 0,
        "notified": set()
    }
    msg = "🔔 Auto‑notify enabled!" if enable else "🔕 Auto‑notify disabled."
    await update.callback_query.answer(msg)
    await update.callback_query.message.edit_reply_markup(reply_markup=None)

async def stop_notify_cmd(update, context):
    bot_state=context.application.bot_data.setdefault("auto_notify",{})
    bot_state[update.effective_user.id]={"enabled":False,"last":0,"notified":set()}
    await update.message.reply_text("🔕 Auto‑notify disabled. Use /match anytime.")

# ───────── notify women when customer approved ─────────
async def notify_women_if_needed(context, cust_lat,cust_lon, customer_id):
    cur=get_conn().cursor()
    # profile data of new customer
    cur.execute("SELECT username,name,age,bio,photo_file_id,phone_number,lat,lon FROM users WHERE telegram_id=?", (customer_id,))
    data=cur.fetchone(); if not data: return
    username,name,age,bio,photo,phone,lat,lon=data
    caption_tpl=f"*{name}*, {age} y/o (~{{}} km)\n{bio}"
    buttons=[[InlineKeyboardButton("✅ Accept",f"accept_{customer_id}"),
              InlineKeyboardButton("❌ Skip","skip_match")]]
    bot_state=context.application.bot_data.setdefault("auto_notify",{})
    now=int(time.time())

    cur.execute("SELECT telegram_id,lat,lon FROM users WHERE role='woman' AND approved=1 AND lat IS NOT NULL AND lon IS NOT NULL")
    for wid,wlat,wlon in cur.fetchall():
        if haversine(cust_lat,cust_lon,wlat,wlon) > MATCH_RADIUS_KM: continue
        state=bot_state.get(wid)
        if not state or not state["enabled"]: continue
        if customer_id in state["notified"]: continue
        if now-state["last"]<NOTIFY_COOLDOWN: continue

        dist=round(haversine(wlat,wlon,lat,lon))
        try:
            await context.bot.send_photo(
                chat_id=wid, photo=photo,
                caption=caption_tpl.format(dist),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            state["last"]=now
            state["notified"].add(customer_id)
        except Exception as e:
            print("Notify error:",e)

def get_match_handlers():
    return [
        CommandHandler("match", match_cmd),
        CommandHandler("stopnotify", stop_notify_cmd),
        CallbackQueryHandler(skip_cb,  pattern="^skip_match$"),
        CallbackQueryHandler(accept_cb,pattern="^accept_\\d+$"),
        CallbackQueryHandler(auto_mode_cb, pattern="^enable_auto$|^disable_auto$")
    ]
