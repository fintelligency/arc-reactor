from commands.telegram_bot import start_bot
from config.config_loader import CONFIG
from zone_generator import generate_zone_file
import datetime
import os

if __name__ == "__main__":
    print("[ArcReactor] Booting Arc Commander...")

    # Ensure yearly zones are generated
    current_year = datetime.datetime.now().year
    zone_file = f"zones/equity_zones_{current_year}.xlsx"
    if not os.path.exists(zone_file):
        print("[Startup] Generating new yearly zone data...")
        generate_zone_file(current_year - 1)

    start_bot(CONFIG)
