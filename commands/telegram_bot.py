from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from zone_generator import generate_zone_file, generate_zone_file_for_symbols

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Arc Commander Activated. Use /refresh_zone <SYMBOL> or /refresh_zone ALL")

async def refresh_zone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args

    if not args:
        await update.message.reply_text("⚠️ Please specify stock(s) or use `/refresh_zone ALL`", parse_mode='Markdown')
        return

    try:
        if args[0].upper() == "ALL":
            generate_zone_file(force=True)
            await update.message.reply_text("✅ All Nifty 50 zones refreshed and pushed to Google Sheet (zones_2025).")
        else:
            symbols = [sym.upper() for sym in args]
            generate_zone_file_for_symbols(symbols)
            await update.message.reply_text(f"✅ Zones refreshed for: {', '.join(symbols)} and updated in GSheet.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


def start_bot(config):
    application = ApplicationBuilder().token(config["TELEGRAM_TOKEN"]).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("refresh_zone", refresh_zone))

    print("[Telegram] 🤖 Arc Commander is live.")
    application.run_polling()
