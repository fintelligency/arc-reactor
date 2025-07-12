from telegram import Bot
from config.config_loader import CONFIG

def send_telegram_alert(message):
    try:
        bot = Bot(token=CONFIG["TELEGRAM_TOKEN"])
        bot.send_message(chat_id=CONFIG["TELEGRAM_CHAT_ID"], text=message)
    except Exception as e:
        print(f"[Alert] ❌ Failed to send Telegram alert: {e}")