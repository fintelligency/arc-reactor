from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram import Update
from config.config_loader import CONFIG
from zone_generator import generate_zone_file, generate_zone_file_for_symbols
import datetime

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Arc Commander Activated.\nUse /refresh_zone ALL or /refresh_zone RELIANCE")

async def refresh_zones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    year = datetime.datetime.now().year - 1

    if not args or args[0].upper() == "ALL":
        df = generate_zone_file(year=year, force=True)
    else:
        symbols = [s.strip().upper() for s in args]
        df = generate_zone_file_for_symbols(symbols, year=year)

    if df is None or "Symbol" not in df.columns:
        await update.message.reply_text("❌ Error: 'Symbol' — no valid zone data returned.")
        return

    updated = df['Symbol'].tolist()
    await update.message.reply_text(f"✅ Zones refreshed & uploaded for: {', '.join(updated)}")

def start_bot(config):
    app = ApplicationBuilder().token(config["TELEGRAM_TOKEN"]).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("refresh_zone", refresh_zones))

    app.run_polling()
