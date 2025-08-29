import pandas as pd
import numpy as np
from utils.nifty_manager import NiftyManager
from entry_signals import scan_multiple


def load_pp_levels(pp_csv):
    df = pd.read_csv(pp_csv)
    pp_map = {}
    for _, row in df.iterrows():
        yr = int(row['Year'])
        sym = row['symbol']
        levels = {
            "PP": row['pp'],
            "S1": row['s1'],
            "S2": row['s2'],
            "S3": row['s3'],
            "R1": row['r1'],
            "R2": row['r2'],
            "R3": row['r3']
        }
        pp_map.setdefault(yr, {})[sym] = levels
    return pp_map


class MockPriceFeed:
    def __init__(self, df):
        self.df = df

    def get_price_row(self, symbol, date=None):
        row = self.df[self.df['symbol'] == symbol]
        if row.empty:
            return None
        r = row.iloc[0]
        return {
            'open': r['open'],
            'high': r['high'],
            'low': r['low'],
            'close': r['close'],
            'volume': r.get('volume', 0)
        }


class BacktestEngine:
    def __init__(self, price_df, pp_csv, nifty_csv, config):
        self.price_df = price_df.copy()
        self.config = config
        self.nifty_mgr = NiftyManager(nifty_csv)
        self.pp_map = load_pp_levels(pp_csv)

        self.positions = pd.DataFrame(columns=[
            'symbol', 'entry_zone', 'entry_price', 'quantity', 'entry_date'
        ])
        self.active_positions = {}
        self.entry_log = []
        self.exit_log = []

        # Protocol-R tracking
        self.removal_dates = {}              # sym -> date of member→non-member flip
        self.protocol_r_exited_syms = set()  # syms already fully exited by Protocol-R
        self._was_member = {}                # sym -> last seen membership (bool)

    def run_backtest(self):
        all_dates = sorted(self.price_df['date'].unique())
        prot_r = self.config.get("PROTOCOL_R", "N")  # "Y" or "N"

        for dt in all_dates:
            dt_ts = pd.to_datetime(dt)
            year_key = int(dt_ts.year)

            day_df = self.price_df[self.price_df['date'] == dt]
            symbols_today = day_df['symbol'].unique().tolist()
            pivots_today = self.pp_map.get(year_key, {})

            # Quick lookups
            day_highs = dict(zip(day_df['symbol'], day_df['high']))
            day_closes = dict(zip(day_df['symbol'], day_df['close']))

            # --- Membership flip detection (member -> non-member) ---
            for sym in symbols_today:
                is_mem = self.nifty_mgr.is_member(sym, dt)
                was_mem = self._was_member.get(sym)
                if was_mem is None:
                    # first time we see the symbol; remember state
                    self._was_member[sym] = is_mem
                else:
                    if was_mem and not is_mem and sym not in self.removal_dates:
                        self.removal_dates[sym] = dt_ts
                        print(f"[Protocol-R Activated] {sym} removed on {dt_ts.date()}")
                    self._was_member[sym] = is_mem

            # --- ENTRY: only while member ---
            for sym in symbols_today:
                if not self.nifty_mgr.is_member(sym, dt):
                    continue

                entries = scan_multiple(
                    symbols=[sym],
                    pivots_map={sym: pivots_today.get(sym, {})},
                    price_feed=MockPriceFeed(day_df),
                    config=self.config,
                    date=dt,
                    current_year=year_key,
                    active_positions=self.active_positions
                )

                for e in entries:
                    if e and e.action == "BUY":
                        self.positions = pd.concat([self.positions, pd.DataFrame([{
                            'symbol': e.symbol,
                            'entry_zone': e.zone,
                            'entry_price': e.price,
                            'quantity': e.qty,
                            'entry_date': dt_ts
                        }])], ignore_index=True)

                        self.entry_log.append({
                            'symbol': e.symbol,
                            'zone': e.zone,
                            'price': e.price,
                            'date': dt_ts
                        })

            # --- EXIT processing ---
            exit_rows = []

            # --- Normal exits for still-members ---
            for idx, pos in self.positions.iterrows():
                sym = pos['symbol']
                zone = pos['entry_zone']
                pivot = pivots_today.get(sym)
                if pivot is None or sym not in day_highs:
                    continue

                high_px = day_highs[sym]
                reason = None
                exit_px = None

                if zone == "S1" and high_px >= pivot["R1"]:
                    reason, exit_px = "R1", pivot["R1"]
                elif zone == "S2" and high_px >= pivot["R2"]:
                    reason, exit_px = "R2", pivot["R2"]
                elif zone == "S3" and high_px >= pivot["R3"]:
                    reason, exit_px = "R3", pivot["R3"]

                if reason:
                    pnl = (exit_px - pos['entry_price']) * pos['quantity']
                    exit_rows.append({
                        'symbol': sym,
                        'entry_price': pos['entry_price'],
                        'exit_price': exit_px,
                        'entry_zone': pos['entry_zone'],
                        'entry_date': pos['entry_date'],
                        'exit_date': dt_ts,
                        'quantity': pos['quantity'],
                        'pnl': pnl,
                        'reason': reason
                    })
                    self.positions.at[idx, 'to_remove'] = True

            # Drop closed positions
            if not self.positions.empty and 'to_remove' in self.positions.columns:
                self.positions = self.positions[self.positions['to_remove'] != True]
                self.positions.drop(columns=['to_remove'], inplace=True)

            if exit_rows:
                self.exit_log.extend(exit_rows)

        # === Unrealized P&L for still-open positions ===
        last_date = pd.to_datetime(self.price_df['date'].max())
        last_df = self.price_df[self.price_df['date'] == last_date]
        last_closes = dict(zip(last_df['symbol'], last_df['close']))

        for _, pos in self.positions.iterrows():
            sym = pos['symbol']
            if sym in last_closes:
                last_close = last_closes[sym]
                unrealized_pnl = (last_close - pos['entry_price']) * pos['quantity']
                self.exit_log.append({
                    'symbol': sym,
                    'entry_price': pos['entry_price'],
                    'exit_price': last_close,
                    'entry_zone': pos['entry_zone'],
                    'entry_date': pos['entry_date'],
                    'exit_date': "OPEN",
                    'quantity': pos['quantity'],
                    'pnl': unrealized_pnl,
                    'reason': "OPEN"
                })
        print(self.exit_log)
        return pd.DataFrame(self.exit_log, columns=[
            'symbol', 'entry_price', 'exit_price', 'entry_zone',
            'entry_date', 'exit_date', 'quantity', 'pnl', 'reason'
        ])
