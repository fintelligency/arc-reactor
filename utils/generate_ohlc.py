import pandas as pd
import yfinance as yf
from tqdm import tqdm
import os, time

# Paths
nifty_csv = os.path.join(os.path.dirname(__file__), '../data/nifty50_membership.csv')
output_csv = os.path.join(os.path.dirname(__file__), '../data/ohlc.csv')
failed_csv = os.path.join(os.path.dirname(__file__), '../data/failed_symbols.csv')

# Load Nifty membership
df_nifty = pd.read_csv(nifty_csv)
df_nifty.columns = df_nifty.columns.str.strip().str.lower()

df_nifty['from_date'] = pd.to_datetime(df_nifty['from_date'], errors='coerce')
df_nifty['to_date']   = pd.to_datetime(df_nifty['to_date'], errors='coerce')
df_nifty['to_date']   = df_nifty['to_date'].fillna(pd.Timestamp.today())

# ✅ Limit to 5 symbols for testing
#df_nifty = df_nifty.head(5)

# Mapping for Yahoo Finance quirks
SYMBOL_MAP = {
    "M&M": "M&M",
    "BAJAJ-AUTO": "BAJAJ-AUTO",
    "HDFCLIFE": "HDFCLIFE",
    "SBILIFE": "SBILIFE"
}

# Final schema
FINAL_COLS = ['date', 'symbol', 'open', 'high', 'low', 'close', 'volume']

all_ohlc = []
failed_symbols = []

# ✅ Safe download with retries
def safe_download(symbol, start, end, retries=3, delay=5):
    for attempt in range(retries):
        try:
            df = yf.download(
                str(symbol),
                start=start,
                end=end,
                progress=False,
                auto_adjust=False
            )
            if isinstance(df, pd.DataFrame) and not df.empty:
                return df
        except Exception as e:
            print(f"⚠️ Error fetching {symbol}, attempt {attempt+1}/{retries}: {e}")
        time.sleep(delay)
    return None

print("Fetching OHLC data for test symbols...")
for _, row in tqdm(df_nifty.iterrows(), total=len(df_nifty)):
    raw_symbol = str(row['symbol']).strip()

    if isinstance(raw_symbol, tuple):
        raw_symbol = raw_symbol[0]

    yahoo_symbol = SYMBOL_MAP.get(raw_symbol, raw_symbol) + ".NS"

    start_date = row['from_date']
    end_date   = row['to_date'] + pd.Timedelta(days=1)  # inclusive

    ohlc = safe_download(yahoo_symbol, start_date, end_date)

    if ohlc is None or ohlc.empty:
        print(f"❌ Failed after retries for {yahoo_symbol}")
        failed_symbols.append(raw_symbol)
        continue

    # Reset index
    ohlc.reset_index(inplace=True)
    ohlc['symbol'] = raw_symbol

    # ✅ flatten multi-index columns
    if isinstance(ohlc.columns, pd.MultiIndex):
        ohlc.columns = [c[0].lower() for c in ohlc.columns]
    else:
        ohlc.columns = [str(c).lower() for c in ohlc.columns]

    print(f"Columns for {raw_symbol}: {ohlc.columns.tolist()}")

    expected = ['date', 'open', 'high', 'low', 'close', 'volume', 'symbol']
    missing = [c for c in expected if c not in ohlc.columns]
    if missing:
        print(f"⚠️ Missing columns for {raw_symbol}: {missing}")
        failed_symbols.append(raw_symbol)
        continue

    ohlc = ohlc[expected].copy()

    # Drop rows with missing values in key columns
    ohlc = ohlc.dropna(subset=['date','open','high','low','close'])

    # Debug: print first 2 rows per symbol
    print(f"\nSample for {raw_symbol}:")
    print(ohlc.head(2))

    all_ohlc.append(ohlc)

    time.sleep(0.5)  # avoid rate limiting

# Combine and save
if all_ohlc:
    final_df = pd.concat(all_ohlc, axis=0, ignore_index=True)  # vertical stacking
    final_df = final_df[FINAL_COLS]  # enforce column order again
    final_df.to_csv(output_csv, index=False)
    print(f"\n✅ OHLC data saved to {output_csv}")
    print(final_df.head(10))  # show preview
else:
    print("🚨 No OHLC data fetched!")

# Report failed
if failed_symbols:
    print("⚠️ Failed symbols:", failed_symbols)
    pd.Series(failed_symbols, name="failed_symbols").to_csv(failed_csv, index=False)
    print(f"📄 Failed symbols list saved to {failed_csv}")
