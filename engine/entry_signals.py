# engine/entry_signals.py

import yfinance as yf
import pandas as pd
import datetime
from config.config_loader import CONFIG
from config.strategy_loader import STRATEGY_CONFIG
from upload.gdrive_sync import read_sheet, append_row
from utils.alert import send_telegram_alert

MAX_YEARLY_CAP = STRATEGY_CONFIG.get("MAX_YEARLY_CAP", 100000)
TRANCHE_SIZE = STRATEGY_CONFIG.get("TRANCHE_SIZE", 25000)
ZONE_FIELDS = ['PP', 'S1', 'S2', 'S3']

def get_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def is_bullish_candle(df):
    return df['Close'].iloc[-1] > df['Open'].iloc[-1]

def is_valid_zone_match(price, zone_price):
    return abs(price - zone_price) / zone_price <= 0.01

def check_signal_for_stock(row, entry_log_df):
    symbol = row['Symbol']
    year = row['Year']
    yf_symbol = symbol + ".NS"

    try:
        df = yf.download(yf_symbol, period="3mo", interval="1d", progress=False, auto_adjust=False)
        if df.empty:
            return

        latest = df.iloc[-1]
        rsi = get_rsi(df['Close']).iloc[-1]
        volume_avg = df['Volume'].rolling(20).mean().iloc[-1]
        volume_current = latest['Volume']
        volume_ratio = round(volume_current / volume_avg, 2) if volume_avg else 0
        cmp = float(latest['Close'])

        stock_entries = entry_log_df[(entry_log_df['Symbol'] == symbol) & (entry_log_df['Year'] == year)]
        active_entries = stock_entries[stock_entries['Status'].str.lower() == 'active']
        capital_used = active_entries['Amount'].sum()
        if capital_used >= MAX_YEARLY_CAP:
            return

        used_zones = active_entries['Zone'].tolist()

        for zone in ZONE_FIELDS:
            zone_price = row[zone]
            if not is_valid_zone_match(cmp, zone_price):
                continue
            if zone in used_zones:
                continue

            if zone in ['S2', 'S3']:
                if rsi >= (40 if zone == 'S2' else 35):
                    continue
                if not is_bullish_candle(df):
                    continue
                if volume_ratio < 1:
                    continue

            msg = f"🟢 *BUY SIGNAL*: {symbol} @ {zone} ₹{cmp:.2f}\n" \
                  f"🧠 RSI: {rsi:.1f} | Volume: {volume_ratio}x | Year: {year}\n" \
                  f"💼 Zone: {zone} | Tranche: ₹{TRANCHE_SIZE:,}"
            send_telegram_alert(msg)

            entry_data = [symbol, year, zone, TRANCHE_SIZE, datetime.date.today().isoformat(), "active"]
            append_row(CONFIG["GSHEET_ID"], "entry_log", entry_data)
            break

    except Exception as e:
        print(f"[SignalEngine] ⚠️ Failed {symbol}: {e}")

def run_signal_engine():
    zone_df = read_sheet(CONFIG["GSHEET_ID"], "trading_zones")
    entry_log_df = read_sheet(CONFIG["GSHEET_ID"], "entry_log")

    for _, row in zone_df.iterrows():
        check_signal_for_stock(row, entry_log_df)

if __name__ == "__main__":
    run_signal_engine()