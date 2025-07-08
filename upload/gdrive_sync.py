import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os
import json

def upload_to_gsheet(df_new, sheet_name="zones_2025"):
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]

    # Load credentials from environment variable
    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)

    sheet = client.open("ArcReactorMaster")
    worksheet = sheet.worksheet(sheet_name)

    # Download existing sheet as DataFrame
    data = worksheet.get_all_records()
    df_existing = pd.DataFrame(data)

    # Replace rows in df_existing with matching symbols from df_new
    for symbol in df_new["Symbol"]:
        df_existing = df_existing[df_existing["Symbol"] != symbol]
    df_combined = pd.concat([df_existing, df_new], ignore_index=True).sort_values(by="Symbol")

    # Reupload
    worksheet.clear()
    worksheet.update([df_combined.columns.values.tolist()] + df_combined.values.tolist())
    print(f"[GSheet] 🔁 Updated rows: {df_new['Symbol'].tolist()}")
