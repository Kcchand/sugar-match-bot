# approval.py
# Placeholder module
# approval.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, ContextTypes
from database import get_conn

async def approval_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    action, uid = q.data.split("_")
    uid = int(uid)
    conn = get_conn(); cur = conn.cursor()

    if action == "approve":
        cur.execute("UPDATE users SET approved=1 WHERE telegram_id=?", (uid,))
        conn.commit()
        await context.bot.send_message(chat_id=uid, text="🎉 Your profile is approved!")
    else:
        cur.execute("DELETE FROM users WHERE telegram_id=?", (uid,))
        conn.commit()
        await context.bot.send_message(chat_id=uid, text="❌ Your profile was rejected.")

    await q.answer()
    await q.message.delete()

def get_approval_handler():
    return CallbackQueryHandler(approval_cb, pattern="^(approve|reject)_")
