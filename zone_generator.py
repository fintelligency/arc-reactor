# zone_generator.py
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
import yfinance as yf
import pandas as pd
import datetime
import os
import requests
import io  # ✅ NEW

def get_nifty50_symbols():
    url = "https://archives.nseindia.com/content/indices/ind_nifty50list.csv"
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))  # ✅ FIXED
        return df["Symbol"].tolist()
    except Exception as e:
        print(f"[Error] Could not fetch Nifty50 list: {e}")
        # fallback static list
        return [
            "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
            "LT", "SBIN", "HINDUNILVR", "ITC", "KOTAKBANK",
            "AXISBANK", "WIPRO", "TECHM", "SUNPHARMA", "BAJFINANCE",
            "ASIANPAINT", "HCLTECH", "ULTRACEMCO", "POWERGRID", "NTPC",
            "NESTLEIND", "ONGC", "HDFCLIFE", "ADANIENT", "COALINDIA",
            "MARUTI", "TITAN", "BAJAJ-AUTO", "BPCL", "EICHERMOT"
        ]
def calculate_fib_pivots(symbol, year):
    yf_symbol = symbol + '.NS'
    start = f"{year}-01-01"
    end = f"{year}-12-31"

    df = yf.download(yf_symbol, start=start, end=end, interval='1mo', progress=False, auto_adjust=True)

    if df.empty:
        return None

    high = df['High'].max()
    low = df['Low'].min()
    close = df['Close'].iloc[-1]

    pp = (high + low + close) / 3
    r = high - low

    return {
        'Symbol': symbol,
        'Year': year,
        'PP': round(pp, 2),
        'S1': round(pp - 0.382 * r, 2),
        'S2': round(pp - 0.618 * r, 2),
        'S3': round(pp - 1.000 * r, 2),
        'R1': round(pp + 0.382 * r, 2),
        'R2': round(pp + 0.618 * r, 2),
        'R3': round(pp + 1.000 * r, 2),
    }


def generate_zone_file(year=None, force=False):
    if not year:
        year = datetime.datetime.now().year - 1  # Use previous year

    path = f"zones/equity_zones_{year+1}.xlsx"

    if os.path.exists(path) and not force:
        print(f"[ZoneGenerator] Zones for {year+1} already exist.")
        return path

    print(f"[ZoneGenerator] Generating zones for {year+1}...")

    symbols = get_nifty50_symbols()
    result = []

    for sym in symbols:
        row = calculate_fib_pivots(sym, year)
        if row:
            result.append(row)

    df = pd.DataFrame(result)
    os.makedirs('zones', exist_ok=True)
    df.to_excel(path, index=False)
    print(f"[ZoneGenerator] Zones generated for year {year+1}: {path}")
    return path


if __name__ == "__main__":
    generate_zone_file()
