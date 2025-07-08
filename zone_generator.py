# zone_generator.py

import yfinance as yf
import pandas as pd
import datetime
import os
import requests


def get_nifty50_symbols():
    url = 'https://www1.nseindia.com/content/indices/ind_nifty50list.csv'
    headers = {'User-Agent': 'Mozilla/5.0'}
    r = requests.get(url, headers=headers)
    df = pd.read_csv(pd.compat.StringIO(r.text))
    return df['Symbol'].str.replace('&', '%26').tolist()


def calculate_fib_pivots(symbol, year):
    yf_symbol = symbol + '.NS'
    start = f"{year}-01-01"
    end = f"{year}-12-31"

    df = yf.download(yf_symbol, start=start, end=end, interval='1mo', progress=False)
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


def generate_zone_file(year=None):
    if not year:
        year = datetime.datetime.now().year - 1  # Use previous year

    path = f"zones/equity_zones_{year+1}.xlsx"
    if os.path.exists(path):
        print(f"[ZoneGenerator] Zones for {year+1} already exist.")
        return path

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
