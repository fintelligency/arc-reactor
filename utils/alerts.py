# utils/alerts.py

from telegram import Bot
from config.config_loader import CONFIG

async def send_telegram_alert(message: str):
    try:
        token = CONFIG.get("TELEGRAM_TOKEN")
        chat_id = CONFIG.get("TELEGRAM_CHAT_ID")

        if not token or not chat_id:
            raise ValueError("Missing token or TELEGRAM_CHAT_ID")

        bot = Bot(token=token)
        await bot.send_message(chat_id=chat_id, text=message)

    except Exception as e:
        print(f"[Alert] ❌ Failed to send Telegram alert: {e}")
