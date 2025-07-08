import json
import os

def load_config():
    config_path = os.path.join("config", "config.json")
    with open(config_path, "r") as f:
        return json.load(f)

CONFIG = load_config()