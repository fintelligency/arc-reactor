import pandas as pd
import yfinance as yf
from datetime import datetime

def load_zone_file():
    current_year = datetime.now().year
    df = pd.read_excel(f"zones/equity_zones_{current_year}.xlsx")
    return df

def fetch_price(symbol):
    try:
        data = yf.download(f"{symbol}.NS", period="1d", interval="1m", progress=False)
        if not data.empty:
            return data['Close'].iloc[-1]
    except Exception as e:
        print(f"[Error] Fetching price for {symbol}: {e}")
    return None