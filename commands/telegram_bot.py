from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from config.config_loader import CONFIG
from engine.entry_signals import check_signal_for_stock
from engine.ic_entry import run_ic_entry_scan
from upload.gdrive_sync import read_sheet
import logging
from telegram import Bot

# === Telegram Command: Start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Arc Commander Activated.\nUse /refresh_zone, /signal SYMBOL, or /ic_entry.")

# === Telegram Command: Signal ===
async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("❓ Usage: /signal SYMBOL")
            return

        symbol = context.args[0].upper()
        sheet_id = CONFIG["GSHEET_ID"]

        zone_df = read_sheet(sheet_id, "trading_zones")
        entry_log_df = read_sheet(sheet_id, "entry_log")

        if symbol not in zone_df["Symbol"].values:
            await update.message.reply_text(f"❌ Symbol {symbol} not found in zone sheet.")
            return

        row = zone_df[zone_df["Symbol"] == symbol].iloc[0]
        check_signal_for_stock(row, entry_log_df)
        await update.message.reply_text(f"✅ Signal checked for {symbol}")

    except Exception as e:
        logging.exception(e)
        await update.message.reply_text(f"❌ Error: {e}")

# === Telegram Command: IC Entry ===
async def ic_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Scanning for Iron Condor opportunities...")
    await run_ic_entry_scan()

# === Start Bot ===
def start_bot(config):
    app = ApplicationBuilder().token(config["TELEGRAM_TOKEN"]).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("signal", signal))
    app.add_handler(CommandHandler("ic_entry", ic_entry))
    app.run_polling()
