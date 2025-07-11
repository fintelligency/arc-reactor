# config/config_loader.py

import os
import json

with open("config/config.json") as f:
    config_data = json.load(f)

CONFIG = {
    "TELEGRAM_TOKEN": os.getenv("TELEGRAM_TOKEN", config_data.get("TELEGRAM_TOKEN")),
    "GSHEET_ID": os.getenv("GSHEET_ID", config_data.get("GSHEET_ID")),
    "GSHEET_CREDS": json.loads(os.environ.get("GOOGLE_CREDENTIALS_JSON", "{}")),
}
