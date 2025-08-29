# test_run.py
import os
import pandas as pd
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 200)

from engine.backtest_engine import BacktestEngine

base = os.path.dirname(__file__)
ohlc_csv        = os.path.join(base, '../data/ohlc.csv')
pp_levels_csv   = os.path.join(base, '../data/hist_pp_levels.csv')
nifty_csv       = os.path.join(base, '../data/nifty50_membership.csv')  # optional

price_df = pd.read_csv(ohlc_csv, parse_dates=['date'])

# Config
config = {
    "ALLOCATION_PER_ZONE": 25000,
    'PROTOCOL_R': 'N',   # enable Protocol-R
    "S2_RSI_MAX": 40,
    "S3_RSI_MAX": 35
}

# Initialize
engine = BacktestEngine(
    price_df=price_df,
    pp_csv=pp_levels_csv,
    nifty_csv=nifty_csv,
    config=config
)

# Optional skip protocol R for testing:
# engine.nifty_mgr.is_member = lambda s, d: True

results = engine.run_backtest()

print("Exit Log:")
print(results)
print("\nEntries:", len(engine.entry_log))
if not results.empty:
    print("Total P&L:", results['pnl'].sum())
else:
    print("No exits triggered.")
