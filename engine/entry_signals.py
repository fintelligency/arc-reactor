import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os
import json
from gspread.utils import ValueInputOption

# === Common Auth Setup ===
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
CREDS_DICT = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
CREDS = ServiceAccountCredentials.from_json_keyfile_dict(CREDS_DICT, SCOPE)
CLIENT = gspread.authorize(CREDS)

# === Upload Full Sheet (Zone Generator) ===
def upload_to_gsheet(df_new, sheet_name="zones_2025"):
    print(f"[GSheet] 🔎 df_new Columns: {getattr(df_new, 'columns', 'N/A')}")
    if not isinstance(df_new, pd.DataFrame):
        raise ValueError("[GSheet] ❌ df_new is not a DataFrame")
    if df_new.empty:
        raise ValueError("[GSheet] ❌ DataFrame is empty before upload.")
    if "Symbol" not in df_new.columns:
        raise ValueError(f"[GSheet] ❌ 'Symbol' column missing. Found: {df_new.columns.tolist()}")

    sheet = CLIENT.open("ArcReactorMaster")
    worksheet = sheet.worksheet(sheet_name)

    try:
        data = worksheet.get_all_records()
        df_existing = pd.DataFrame(data)
        if df_existing.empty or "Symbol" not in df_existing.columns:
            print("[GSheet] ⚠️ Existing sheet missing or corrupt. Initializing new sheet.")
            df_existing = pd.DataFrame(columns=df_new.columns)
    except Exception as e:
        print(f"[GSheet] ⚠️ Failed to fetch existing data: {e}")
        df_existing = pd.DataFrame(columns=df_new.columns)

    for symbol in df_new["Symbol"]:
        df_existing = df_existing[df_existing["Symbol"] != symbol]
    df_combined = pd.concat([df_existing, df_new], ignore_index=True).sort_values(by="Symbol")

    worksheet.clear()
    worksheet.update([df_combined.columns.values.tolist()] + df_combined.values.tolist())
    print(f"[GSheet] 🔁 Updated rows: {df_new['Symbol'].tolist()}")

# === Read Sheet for Signal Engine ===
def read_sheet(sheet_id, sheet_name):
    try:
        sheet = CLIENT.open_by_key(sheet_id).worksheet(sheet_name)
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        return df
    except Exception as e:
        print(f"[GSheet] ❌ Read failed: {e}")
        return pd.DataFrame()

# === Append Row for Signal Engine ===
def append_row(sheet_id, sheet_name, row_data):
    try:
        sheet = CLIENT.open_by_key(sheet_id).worksheet(sheet_name)
        sheet.append_row(row_data, value_input_option=ValueInputOption.user_entered)
        print(f"[GSheet] ✅ Appended to {sheet_name}: {row_data}")
    except Exception as e:
        print(f"[GSheet] ❌ Append failed: {e}")

# Optional
__all__ = ["upload_to_gsheet", "read_sheet", "append_row"]