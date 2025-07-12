# config/pp_loader.py

import json

try:
    with open("config/pp_settings.json") as f:
        PP_SETTINGS = json.load(f)
except Exception as e:
    print(f"[Config] ⚠️ Failed to load pp_settings.json: {e}")
    PP_SETTINGS = {}
