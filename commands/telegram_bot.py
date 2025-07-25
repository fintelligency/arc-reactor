from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler
)
from telegram.ext.filters import MessageFilter
from config.config_loader import CONFIG
from engine.entry_signals import check_signal_for_stock
from engine.ic_scanner import find_adaptive_ic_from_csv, log_and_alert_ic_candidates
from upload.gdrive_sync import read_sheet
import logging
import os
import tempfile

# === Custom CSV File Filter ===
class CSVFileFilter(MessageFilter):
    def filter(self, message):
        return message.document and message.document.file_name.endswith(".csv")

csv_filter = CSVFileFilter()

# === Telegram Command: Start ===
async def start(update: Update, _: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Arc Commander Activated.\nUse /refresh_zone, /signal SYMBOL, or upload IC CSV using /ic_entry.")

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

# === Telegram CSV Upload for IC ===
async def upload_ic_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.endswith(".csv"):
        await update.message.reply_text("⚠️ Please upload a valid CSV file.")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, doc.file_name)
        new_file = await context.bot.get_file(doc.file_id)
        await new_file.download_to_drive(file_path)

        try:
            # 🔒 Detect locked mode from filename
            locked_mode = "locked" in doc.file_name.lower()

            # 🧠 Pass locked_mode to IC scanner
            ic_list = await find_adaptive_ic_from_csv(file_path)

            if ic_list:
                await log_and_alert_ic_candidates(ic_list)
                if locked_mode:
                    await update.message.reply_text("🔒 Locked IC strategy scanned and logged.")
                else:
                    await update.message.reply_text("✅ IC candidates scanned and logged.")
            else:
                await update.message.reply_text("⚠️ No valid ICs found.")

        except Exception as e:
            await update.message.reply_text(f"❌ Failed to scan IC: {e}")

# === Telegram Command: Fetch NSE Data ===
async def fetch_nse(update: Update, _: ContextTypes.DEFAULT_TYPE):
    try:
        from utils.nse_oc_fetcher import fetch_nse_option_chain

        symbol = "BANKNIFTY"
        option_chain = fetch_nse_option_chain(symbol)

        if isinstance(option_chain, list) and len(option_chain) > 0:
            await update.message.reply_text(f"✅ Fetched {len(option_chain)} rows for {symbol}")
        else:
            await update.message.reply_text("⚠️ Empty option chain or invalid response")

    except Exception as e:
        logging.exception(e)
        await update.message.reply_text(f"❌ Failed to fetch NSE data: {e}")


# === Start Bot ===
def start_bot(config):
    app = ApplicationBuilder().token(config["TELEGRAM_TOKEN"]).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("signal", signal))
    app.add_handler(MessageHandler(csv_filter, upload_ic_csv))
    app.add_handler(CommandHandler("fetch_nse", fetch_nse))
    app.run_polling()
