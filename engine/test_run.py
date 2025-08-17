# test_run.py
import os
import pandas as pd
from datetime import datetime
from engine.backtest_engine import BacktestEngine

# -----------------------------
# MOCK DATA
symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK"]
dates = pd.date_range(start="2025-01-01", end="2025-01-10")

# Mock daily OHLCV
price_rows = []
for dt in dates:
    for sym in symbols:
        price_rows.append({
            "date": dt,
            "symbol": sym,
            "open": 100,
            "high": 105,
            "low": 95,
            "close": 100 + (hash(sym+str(dt)) % 10),  # pseudo-random close
            "volume": 1000 + (hash(sym) % 500)
        })
price_df = pd.DataFrame(price_rows)

# Dummy R levels
r_levels_rows = []
for sym in symbols:
    r_levels_rows.append({"symbol": sym, "R1": 105, "R2": 110, "R3": 115})
r_levels_df = pd.DataFrame(r_levels_rows)

# Dummy pivots for entry zones
pivots_map = {sym: {"P": 100, "S1": 95, "S2": 90, "S3": 85} for sym in symbols}

# -----------------------------
# CONFIG
config = {
    "ALLOCATION_PER_ZONE": 25000,
    "S2_RSI_MAX": 40,
    "S3_RSI_MAX": 35,
    "PIVOTS_MAP": pivots_map
}

# -----------------------------
# Backtest
nifty_csv = os.path.join(os.path.dirname(__file__), '../data/nifty50_membership.csv')

backtester = BacktestEngine(
    price_df=price_df,
    r_levels_df=r_levels_df,
    nifty_csv=nifty_csv,
    config=config
)

# -----------------------------
# Inject mock Protocol R removal for RELIANCE on 2025-01-05
def mock_nifty_removed(symbol, date):
    if symbol == "RELIANCE" and date >= pd.Timestamp("2025-01-05"):
        return False  # simulate removal
    return True

backtester.nifty_mgr.is_member = mock_nifty_removed

# -----------------------------
# Run backtest
exits_log_df = backtester.run_backtest()

# -----------------------------
# Add mock entry_price and entry_zone for P&L
# Assuming every exit had a matching entry at pivot price
exits_log_df['entry_zone'] = exits_log_df['reason'].str.split('->').str[0].str.strip()
exits_log_df['entry_price'] = exits_log_df['entry_zone'].map({
    'PP': 100, 'S1': 95, 'S2': 90, 'S3': 85
})
exits_log_df['quantity'] = config['ALLOCATION_PER_ZONE'] // exits_log_df['entry_price']

# Compute P&L
exits_log_df['pnl'] = (exits_log_df['exit_price'] - exits_log_df['entry_price']) * exits_log_df['quantity']

# -----------------------------
# Zone-wise P&L breakdown
zone_pnl = exits_log_df.groupby('entry_zone')['pnl'].agg(['count','sum','mean','min','max']).reset_index()

# Symbol-wise P&L summary
symbol_pnl = exits_log_df.groupby('symbol')['pnl'].agg(['count','sum','mean','min','max']).reset_index()

# Total P&L
total_pnl = exits_log_df['pnl'].sum()

# -----------------------------
# Show results
print("\n=== Exit Log ===")
print(exits_log_df)

print("\n=== Zone-wise P&L ===")
print(zone_pnl)

print("\n=== Symbol-wise P&L ===")
print(symbol_pnl)

print("\n=== Total P&L ===")
print(total_pnl)
