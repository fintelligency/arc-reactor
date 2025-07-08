from telegram.ext import Updater, CommandHandler
from config.config_loader import CONFIG
from zone_generator import generate_zone_file
import datetime

def start(update, context):
    update.message.reply_text("🤖 Arc Commander Activated.\nUse /refresh_zones to update PP zones.")

def refresh_zones(update, context):
    year = datetime.datetime.now().year - 1
    file_path = generate_zone_file(year)
    update.message.reply_text(f"✅ Zones refreshed.\nSaved: `{file_path}`", parse_mode='Markdown')

def start_bot(config):
    updater = Updater(config["TELEGRAM_TOKEN"])
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("refresh_zones", refresh_zones))

    updater.start_polling()
    updater.idle()
