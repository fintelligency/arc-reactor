import pandas as pd
import yfinance as yf
from tqdm import tqdm
import os

nifty_csv = os.path.join(os.path.dirname(__file__), '../data/nifty50_membership.csv')
output_csv = os.path.join(os.path.dirname(__file__), '../data/ohlc.csv')

df_nifty = pd.read_csv(nifty_csv)
df_nifty.columns = df_nifty.columns.str.strip().str.lower()

df_nifty['from_date'] = pd.to_datetime(df_nifty['from_date'], errors='coerce')
df_nifty['to_date']   = pd.to_datetime(df_nifty['to_date'], errors='coerce')
df_nifty['to_date'] = df_nifty['to_date'].fillna(pd.Timestamp.today())

all_ohlc = []
failed_symbols = []

print("Fetching OHLC data for Nifty 50 symbols...")
for _, row in tqdm(df_nifty.iterrows(), total=len(df_nifty)):
    symbol = str(row['symbol']).strip() + ".NS"
    start_date = row['from_date']
    end_date   = row['to_date']

    try:
        ohlc = yf.download(symbol, start=start_date, end=end_date, progress=False)
        if ohlc.empty:
            print(f"Warning: No data for {symbol}")
            failed_symbols.append(symbol)
            continue

        ohlc.reset_index(inplace=True)
        ohlc['symbol'] = row['symbol']
        ohlc = ohlc[['Date','symbol','Open','High','Low','Close','Volume']]
        ohlc.rename(columns={'Date':'date','Open':'open','High':'high','Low':'low','Close':'close','Volume':'volume'}, inplace=True)

        all_ohlc.append(ohlc)
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        failed_symbols.append(symbol)

if all_ohlc:
    final_df = pd.concat(all_ohlc, ignore_index=True)
    final_df.to_csv(output_csv, index=False)
    print(f"OHLC data saved to {output_csv}")
else:
    print("No OHLC data fetched!")

if failed_symbols:
    print("Failed symbols:", failed_symbols)