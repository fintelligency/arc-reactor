from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler
)
from telegram.ext.filters import MessageFilter
from config.config_loader import CONFIG
from engine.ic_scanner import find_adaptive_ic_from_csv, log_and_alert_ic_candidates
from upload.gdrive_sync import read_sheet
from zone_generator import generate_zone_file
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
    await update.message.reply_text(
        "🤖 *Arc Commander Activated.*\n\n"
        "Available commands:\n"
        "• /refresh\\_zone — Regenerate Fibonacci pivot zones for all Nifty50 stocks\n"
        "• /signal SYMBOL — Check signal status for a specific stock\n"
        "• Upload a `.csv` option chain file → IC Scanner runs automatically",
        parse_mode="Markdown"
    )

# === Helper: Check signal for a stock ===
def check_signal_for_stock(row, entry_log_df):
    """
    Checks if a symbol is near a key pivot zone and whether a recent entry already exists.
    Returns a formatted status string.
    """
    symbol = str(row.get("Symbol", "")).upper()

    # Check for existing entry in log
    already_entered = False
    if not entry_log_df.empty and "Symbol" in entry_log_df.columns:
        already_entered = symbol in entry_log_df["Symbol"].str.upper().values

    zones = {
        "PP": row.get("PP"),
        "S1": row.get("S1"),
        "S2": row.get("S2"),
        "S3": row.get("S3"),
        "R1": row.get("R1"),
        "R2": row.get("R2"),
        "R3": row.get("R3"),
    }

    zone_lines = "\n".join([f"  {k}: ₹{v}" for k, v in zones.items() if v])
    status = "⚠️ Entry already exists in log" if already_entered else "✅ No active entry — zone is open"

    return (
        f"📊 *{symbol} Signal Status*\n"
        f"{status}\n\n"
        f"*Pivot Levels:*\n{zone_lines}"
    )

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

        if zone_df.empty or "Symbol" not in zone_df.columns:
            await update.message.reply_text("❌ Zone sheet is empty or unreachable.")
            return

        if symbol not in zone_df["Symbol"].values:
            await update.message.reply_text(f"❌ Symbol *{symbol}* not found in zone sheet.", parse_mode="Markdown")
            return

        row = zone_df[zone_df["Symbol"] == symbol].iloc[0]
        msg = check_signal_for_stock(row, entry_log_df)
        await update.message.reply_text(msg, parse_mode="Markdown")

    except Exception as e:
        logging.exception(e)
        await update.message.reply_text(f"❌ Error: {e}")

# === Telegram Command: Refresh Zone ===
async def refresh_zone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Regenerating pivot zones for all Nifty50 stocks... This may take a few minutes.")
    try:
        df = generate_zone_file(force=True)
        if df is not None:
            await update.message.reply_text(f"✅ Zone file refreshed successfully. {len(df)} symbols updated.")
        else:
            await update.message.reply_text("❌ Zone generation failed. Check logs.")
    except Exception as e:
        logging.exception(e)
        await update.message.reply_text(f"❌ Error refreshing zones: {e}")

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

# === Start Bot ===
def start_bot(config):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    app = ApplicationBuilder().token(config["TELEGRAM_TOKEN"]).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("signal", signal))
    app.add_handler(CommandHandler("refresh_zone", refresh_zone))
    app.add_handler(MessageHandler(csv_filter, upload_ic_csv))
    app.run_polling()
