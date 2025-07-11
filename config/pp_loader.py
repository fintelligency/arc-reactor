# config/strategy_loader.py

import json

try:
    with open("config/pp_settings.json") as f:
        STRATEGY_CONFIG = json.load(f)
except Exception as e:
    print(f"[Config] ⚠️ Failed to load strategy_settings.json: {e}")
    STRATEGY_CONFIG = {}
