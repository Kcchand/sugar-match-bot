from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, ContextTypes
from database import get_conn

async def approval_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    action, uid = q.data.split("_"); uid = int(uid)

    conn = get_conn(); cur = conn.cursor()

    if action == "approve":
        cur.execute("UPDATE users SET approved=1 WHERE telegram_id=?", (uid,))
        conn.commit()

        cur.execute("SELECT role FROM users WHERE telegram_id=?", (uid,))
        role_row = cur.fetchone()
        role = role_row[0] if role_row else None

        if role == "woman":
            await context.bot.send_message(
                chat_id=uid,
                text=(
                    "🎉 Your profile is approved!\n\n"
                    "Tap the button below anytime to browse Sugar Customers near you."
                ),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔍 Browse Matches", callback_data="browse_matches")]
                ])
            )
        else:  # customer
            await context.bot.send_message(
                chat_id=uid,
                text=(
                    "✅ Your profile is approved! Sugar Women in your area can now "
                    "view you. If someone likes your profile, expect a direct DM! 🍬"
                )
            )

    else:  # reject
        cur.execute("DELETE FROM users WHERE telegram_id=?", (uid,))
        conn.commit()
        await context.bot.send_message(chat_id=uid, text="❌ Your profile was rejected.")

    await q.message.delete()

async def browse_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await context.bot.send_message(chat_id=update.effective_user.id, text="/match")

def get_approval_handler():
    return [
        CallbackQueryHandler(approval_cb, pattern="^(approve|reject)_"),
        CallbackQueryHandler(browse_cb, pattern="^browse_matches$")
    ]
