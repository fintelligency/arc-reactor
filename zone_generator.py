import ssl
ssl._create_default_https_context = ssl._create_unverified_context

import yfinance as yf
import pandas as pd
import datetime
import os
import requests
import io
import json
from upload.gdrive_sync import upload_to_gsheet

def get_nifty50_symbols():
    url = "https://archives.nseindia.com/content/indices/ind_nifty50list.csv"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        return df["Symbol"].tolist()
    except Exception as e:
        print(f"[ZoneGen] ⚠️ NSE fetch failed: {e}")
        try:
            with open("config/nifty50_fallback.json", "r") as f:
                data = json.load(f)
                return data["symbols"]
        except Exception as e:
            print(f"[ZoneGen] ❌ Fallback JSON failed: {e}")
            return []

def calculate_fib_pivots(symbol, year):
    try:
        yf_symbol = symbol + ".NS"
        start = f"{year}-01-01"
        end = f"{year}-12-31"

        df = yf.download(yf_symbol, start=start, end=end, interval='1d', progress=False, auto_adjust=True)

        if df.empty or 'Close' not in df.columns:
            raise ValueError("No valid data")

        df.dropna(inplace=True)

        high = float(df['High'].max().item())
        low = float(df['Low'].min().item())
        close = float(df['Close'].iloc[-1].item())

        pp = (high + low + close) / 3
        r = high - low

        return {
            'Symbol': symbol,
            'Year': int(year + 1),
            'PP': round(pp, 2),
            'S1': round(pp - 0.382 * r, 2),
            'S2': round(pp - 0.618 * r, 2),
            'S3': round(pp - 1.000 * r, 2),
            'R1': round(pp + 0.382 * r, 2),
            'R2': round(pp + 0.618 * r, 2),
            'R3': round(pp + 1.000 * r, 2)
        }

    except Exception as e:
        print(f"[ZoneGen] ⚠️ Skipping {symbol}: {e}")
        return None

def generate_zone_file(year=None, force=False):
    if not year:
        year = datetime.datetime.now().year - 1

    symbols = get_nifty50_symbols()
    result = []

    for sym in symbols:
        row = calculate_fib_pivots(sym, year)
        if row:
            result.append(row)

    if not result:
        print("[ZoneGen] ❌ No zone data generated. Check API/data source.")
        return None

    df = pd.DataFrame(result)
    upload_to_gsheet(df, sheet_name="zones_2025")
    return df

def generate_zone_file_for_symbols(symbols, year=None):
    if not year:
        year = datetime.datetime.now().year - 1

    result = []
    for sym in symbols:
        row = calculate_fib_pivots(sym, year)
        if row:
            result.append(row)

    if not result:
        print("[ZoneGen] ❌ No custom zone data generated.")
        return None

    df = pd.DataFrame(result)
    upload_to_gsheet(df, sheet_name="zones_2025")
    return df

# ✅ Make functions available for import
__all__ = ["generate_zone_file", "generate_zone_file_for_symbols"]

if __name__ == "__main__":
    generate_zone_file(force=True)
