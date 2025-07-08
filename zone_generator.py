import ssl
ssl._create_default_https_context = ssl._create_unverified_context

import yfinance as yf
import pandas as pd
import datetime
import os
import requests
import io

def get_nifty50_symbols():
    url = "https://archives.nseindia.com/content/indices/ind_nifty50list.csv"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        return df["Symbol"].tolist()
    except Exception as e:
        print(f"[ZoneGen] ⚠️ Failed to fetch Nifty50 list: {e}")
        return [
            "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
            "LT", "SBIN", "HINDUNILVR", "ITC", "KOTAKBANK",
            "AXISBANK", "WIPRO", "TECHM", "SUNPHARMA", "BAJFINANCE",
            "ASIANPAINT", "HCLTECH", "ULTRACEMCO", "POWERGRID", "NTPC",
            "NESTLEIND", "ONGC", "HDFCLIFE", "ADANIENT", "COALINDIA",
            "MARUTI", "TITAN", "BAJAJ-AUTO", "BPCL", "EICHERMOT"
        ]

def calculate_fib_pivots(symbol, year):
    try:
        yf_symbol = symbol + ".NS"
        start = f"{year}-01-01"
        end = f"{year}-12-31"

        df = yf.download(yf_symbol, start=start, end=end, interval='1mo', progress=False, auto_adjust=True)

        if df.empty or 'Close' not in df.columns:
            raise ValueError("Empty or invalid data")

        df.dropna(inplace=True)

        high = float(df['High'].max())
        low = float(df['Low'].min())
        close = float(df['Close'].dropna().values[-1])  # ✅ Ensure scalar float

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

    path = f"zones/equity_zones_{year + 1}.xlsx"

    if os.path.exists(path) and not force:
        print(f"[ZoneGen] Zones for {year + 1} already exist.")
        return path

    print(f"[ZoneGen] 🚀 Generating zones for year {year + 1}...")

    symbols = get_nifty50_symbols()
    result = []

    for sym in symbols:
        row = calculate_fib_pivots(sym, year)
        if row:
            result.append(row)

    if not result:
        print("[ZoneGen] ❌ No data generated. Please check connection or ticker list.")
        return None

    df = pd.DataFrame(result)
    os.makedirs('zones', exist_ok=True)

    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Zones")
        workbook = writer.book
        worksheet = writer.sheets["Zones"]

        float_fmt = workbook.add_format({'num_format': '#,##0.00'})
        for i, col in enumerate(df.columns):
            if pd.api.types.is_float_dtype(df[col]):
                worksheet.set_column(i, i, 12, float_fmt)
            else:
                worksheet.set_column(i, i, 20)

    print(f"[ZoneGen] ✅ Zones saved: {path}")
    return path

if __name__ == "__main__":
    generate_zone_file(force=True)
