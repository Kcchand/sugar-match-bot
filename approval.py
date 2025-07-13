from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, ContextTypes
from database import get_conn
import time
from matcher import notify_women_if_needed

async def approval_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    action, uid = q.data.split("_"); uid = int(uid)
    conn = get_conn(); cur = conn.cursor()

    if action == "approve":
        now=int(time.time())
        cur.execute("UPDATE users SET approved=1, approved_at=? WHERE telegram_id=?", (now, uid))
        conn.commit()

        cur.execute("SELECT role, lat, lon FROM users WHERE telegram_id=?", (uid,))
        role, lat, lon = cur.fetchone()

        if role == "woman":
            await context.bot.send_message(
                uid,
                "🎉 Your profile is approved! Use /match to browse Sugar Customers.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔍 Browse Matches", callback_data="browse_matches")]
                ])
            )
        else:
            await context.bot.send_message(uid, "✅ You're approved! A Sugar Woman may DM you soon.")
            if lat and lon:
                await notify_women_if_needed(context, lat, lon, customer_id=uid)
    else:
        cur.execute("DELETE FROM users WHERE telegram_id=?", (uid,))
        conn.commit()
        await context.bot.send_message(uid, "❌ Your profile was rejected.")
    await q.message.delete()

async def browse_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from matcher import match_cmd
    await match_cmd(update, context)

def get_approval_handler():
    return [
        CallbackQueryHandler(approval_cb, pattern="^(approve|reject)_"),
        CallbackQueryHandler(browse_cb, pattern="^browse_matches$")
    ]
