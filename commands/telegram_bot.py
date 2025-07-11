from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from config.config_loader import CONFIG
from engine.entry_signals import check_signal_for_stock
from upload.gdrive_sync import read_sheet
import logging
from telegram import Bot
from config.config_loader import CONFIG

# === Telegram Command: Start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Arc Commander Activated.\nUse /refresh_zone or /signal SYMBOL.")

# === Telegram Command: Refresh Zones (already present) ===
# async def refresh_zones(...)

# === NEW: Telegram Command: Signal ===
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

# === Start Bot ===
def start_bot(config):
    app = ApplicationBuilder().token(config["TELEGRAM_TOKEN"]).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("signal", signal))
    # app.add_handler(CommandHandler("refresh_zone", refresh_zones)) ← already present
    app.run_polling()
