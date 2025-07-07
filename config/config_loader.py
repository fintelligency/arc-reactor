import os

def load_config():
    return {
        "bot_token": os.getenv("TELEGRAM_BOT_TOKEN"),
        "mode": os.getenv("MODE", "bot"),
    }
