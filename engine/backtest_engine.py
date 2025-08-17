# backtest_engine.py
import pandas as pd
from datetime import datetime, timedelta
from utils.nifty_manager import NiftyManager
from entry_signals import scan_multiple, check_single_zone, EntryResult
from exit_signals import ExitSignals

class MockGDriveSync:
    def __init__(self, positions_df=None):
        self.positions_df = positions_df

    def get_open_positions(self, symbol):
        if self.positions_df is None:
            return []
        return self.positions_df[
            (self.positions_df['symbol'] == symbol) &
            (self.positions_df.get('status', 'open') == 'open')
        ].to_dict('records')

    def log_entry(self, symbol, zone, qty, price, date, capital):
        if self.positions_df is not None:
            new_row = {
                'symbol': symbol,
                'entry_zone': zone,
                'entry_price': price,
                'quantity': qty,
                'removed_on': None,
                'protocol_r_active': False,
                'status': 'open'
            }
            self.positions_df = pd.concat([self.positions_df, pd.DataFrame([new_row])], ignore_index=True)

class BacktestEngine:
    def __init__(self, price_df, r_levels_df, nifty_csv, config):
        self.price_df = price_df
        self.r_levels = r_levels_df
        self.nifty_mgr = NiftyManager(nifty_csv)
        self.positions = pd.DataFrame(columns=['symbol','entry_zone','entry_price','quantity','removed_on','protocol_r_active','status'])
        self.exits_log = []
        self.config = config
        self.gdrive_sync = MockGDriveSync(self.positions)

    def run_backtest(self):
        all_dates = sorted(self.price_df['date'].unique())
        for dt in all_dates:
            today_prices = self.price_df[self.price_df['date'] == dt]
            price_lookup = dict(zip(today_prices['symbol'], today_prices['close']))

            # --- ENTRY SIGNALS ---
            symbols_today = today_prices['symbol'].tolist()
            new_entries: list[EntryResult] = scan_multiple(
                symbols=symbols_today,
                pivots_map=self.config['PIVOTS_MAP'],
                price_feed=MockPriceFeed(today_prices),
                gdrive_sync=self.gdrive_sync,
                dhan_orders=MockDhanOrders(),
                config=self.config,
                alerts=None,
                date=dt
            )

            for entry in new_entries:
                self.positions = pd.concat([self.positions, pd.DataFrame([{
                    'symbol': entry.symbol,
                    'entry_zone': entry.zone,
                    'entry_price': entry.price,
                    'quantity': entry.qty,
                    'removed_on': None,
                    'protocol_r_active': False,
                    'status': 'open'
                }])], ignore_index=True)

            # --- EXIT SIGNALS ---
            exit_engine = ExitSignals(self.positions, self.nifty_mgr, self.r_levels)
            exit_engine.check_protocol_r(dt, price_lookup)  # Protocol R marking
            exits = exit_engine.execute_exits(dt, price_lookup)
            self.exits_log.extend(exits)

        return pd.DataFrame(self.exits_log)

# --- MOCK ADAPTERS ---
class MockPriceFeed:
    def __init__(self, today_prices_df):
        self.today_prices_df = today_prices_df

    def get_price_row(self, symbol, date=None):
        row = self.today_prices_df[self.today_prices_df['symbol'] == symbol]
        if row.empty:
            return None
        r = row.iloc[0]
        return {
            'open': r['open'],
            'high': r['high'],
            'low': r['low'],
            'close': r['close'],
            'volume': r['volume'],
            'rsi': 40,       # placeholder
            'vol_avg': r['volume'] * 0.8
        }

class MockDhanOrders:
    def place_market_buy(self, symbol, qty):
        return {'filled_price': 100}  # mock price

# -----------------------------
# Example usage:
# price_df = pd.read_csv("daily_prices.csv", parse_dates=['date'])
# r_levels_df = pd.read_csv("r_levels.csv")
# config = {
#     "ALLOCATION_PER_ZONE": 25000,
#     "S2_RSI_MAX": 40,
#     "S3_RSI_MAX": 35,
#     "PIVOTS_MAP": {}  # symbol -> {"P":.., "S1":.., "S2":.., "S3":..}
# }
# backtester = BacktestEngine(price_df, r_levels_df, "data/nifty50_membership.csv", config)
# exits_log_df = backtester.run_backtest()
# exits_log_df.to_csv("backtest_exits.csv", index=False)