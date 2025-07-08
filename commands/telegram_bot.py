from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from config.config_loader import CONFIG
from zone_generator import generate_zone_file
import datetime

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Arc Commander Activated.\nUse /refresh_zones to update PP zones."
    )

async def refresh_zones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    year = datetime.datetime.now().year - 1
    file_path = generate_zone_file(year)
    await update.message.reply_text(
        f"✅ Zones refreshed.\nSaved: `{file_path}`", parse_mode='Markdown'
    )

def start_bot(config):
    app = ApplicationBuilder().token(config["TELEGRAM_TOKEN"]).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("refresh_zones", refresh_zones))

    print("[Telegram] Arc Commander is up and ready.")
    app.run_polling()
