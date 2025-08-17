# exit_signals.py
import pandas as pd
from datetime import timedelta

class ExitSignals:
    def __init__(self, positions_df, nifty_manager, r_levels_df):
        """
        positions_df: DataFrame with open positions
            Columns: ['symbol','entry_zone','entry_price','quantity','removed_on','protocol_r_active']
        nifty_manager: instance of NiftyManager (provides current and historical membership)
        r_levels_df: DataFrame with R-levels for each symbol
            Columns: ['symbol','R1','R2','R3']
        """
        self.positions = positions_df
        self.nifty = nifty_manager
        self.r_levels = r_levels_df

    def check_protocol_r(self, current_date, price_lookup):
        """Mark positions for Protocol R if stock removed from Nifty."""
        current_nifty = self.nifty.get_symbols_on_date(current_date)
        for idx, pos in self.positions.iterrows():
            symbol = pos['symbol']
            if symbol not in current_nifty and not pos.get('protocol_r_active', False):
                self.positions.at[idx, 'protocol_r_active'] = True
                self.positions.at[idx, 'removed_on'] = current_date

    def execute_exits(self, current_date, price_lookup):
        """
        Execute exits:
            - Zone-based exits
            - Protocol R exits
        price_lookup: dict {symbol: current_price}
        Returns list of exits: [{'symbol','exit_price','quantity','reason'}]
        """
        exits = []
        # First, handle Protocol R
        for symbol in self.positions['symbol'].unique():
            proto_positions = self.positions[(self.positions['symbol'] == symbol) & (self.positions['protocol_r_active'] == True)]
            if proto_positions.empty:
                continue

            r_vals = self.r_levels.loc[self.r_levels['symbol'] == symbol]
            if r_vals.empty:
                continue
            R_levels = r_vals.iloc[0][['R1','R2','R3']].values
            current_price = price_lookup.get(symbol)
            removed_on = proto_positions['removed_on'].iloc[0]

            # Exit if any R hit
            if current_price >= min(R_levels):
                # Exit all positions for this symbol
                for idx, pos in proto_positions.iterrows():
                    exits.append({
                        'symbol': symbol,
                        'exit_price': current_price,
                        'quantity': pos['quantity'],
                        'reason': 'Protocol R - R-level hit'
                    })
                    self.positions.drop(idx, inplace=True)
            # Exit after 12 months if no R hit
            elif current_date >= removed_on + timedelta(days=365):
                for idx, pos in proto_positions.iterrows():
                    exits.append({
                        'symbol': symbol,
                        'exit_price': current_price,
                        'quantity': pos['quantity'],
                        'reason': 'Protocol R - 12 months hold'
                    })
                    self.positions.drop(idx, inplace=True)

        # Next, handle normal zone-based exits (S1->R1, S2->R2, S3->R3)
        for idx, pos in self.positions.iterrows():
            if pos.get('protocol_r_active', False):
                continue  # already handled
            symbol = pos['symbol']
            entry_zone = pos['entry_zone']
            current_price = price_lookup.get(symbol)
            r_vals = self.r_levels.loc[self.r_levels['symbol'] == symbol]
            if r_vals.empty:
                continue
            if entry_zone == 'S1' and current_price >= r_vals.iloc[0]['R1']:
                exits.append({'symbol': symbol, 'exit_price': current_price, 'quantity': pos['quantity'], 'reason': 'S1 -> R1'})
                self.positions.drop(idx, inplace=True)
            elif entry_zone == 'S2' and current_price >= r_vals.iloc[0]['R2']:
                exits.append({'symbol': symbol, 'exit_price': current_price, 'quantity': pos['quantity'], 'reason': 'S2 -> R2'})
                self.positions.drop(idx, inplace=True)
            elif entry_zone == 'S3' and current_price >= r_vals.iloc[0]['R3']:
                exits.append({'symbol': symbol, 'exit_price': current_price, 'quantity': pos['quantity'], 'reason': 'S3 -> R3'})
                self.positions.drop(idx, inplace=True)
            # PP positions are held (unless Protocol R triggered)

        return exits