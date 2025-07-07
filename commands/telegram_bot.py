from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Arc Commander Activated ✅")

def start_bot(config):
    app = ApplicationBuilder().token(config['bot_token']).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling()
