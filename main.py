import os
import certifi
os.environ["SSL_CERT_FILE"] = certifi.where()

from config.config_loader import load_config
from commands.telegram_bot import start_bot
from backtest.backtest import run_backtest

CONFIG = load_config()
mode = CONFIG.get("mode", "bot")

if mode == "bot":
    print("[ArcReactor] Launching Telegram Commander...")
    start_bot(CONFIG)
elif mode == "backtest":
    print("[ArcReactor] Running Backtest...")
    run_backtest(CONFIG)
else:
    print("❌ Unknown mode. Use mode=bot or mode=backtest")