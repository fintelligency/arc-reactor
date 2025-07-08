from commands.telegram_bot import start_bot
from config.config_loader import CONFIG

if __name__ == "__main__":
    print("[ArcReactor] Launching Telegram Commander...")
    start_bot(CONFIG)
