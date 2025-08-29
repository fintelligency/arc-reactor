"""
Utility class to manage Nifty50 membership based on a CSV file.
CSV MUST have columns: symbol, from_date, to_date
"""

import pandas as pd

class NiftyManager:
    def __init__(self, csv_path):
        """
        csv_path: path to CSV with columns:
            symbol, from_date, to_date
        where to_date can be blank for currently active.
        """
        df = pd.read_csv(csv_path)
        df.columns = [c.strip().lower() for c in df.columns]

        required = {"symbol","from_date","to_date"}
        if not required.issubset(set(df.columns)):
            raise ValueError(f"CSV must contain {required}")

        # parse dates
        df['from_date'] = pd.to_datetime(df['from_date'], errors='coerce')
        df['to_date']   = pd.to_datetime(df['to_date'],   errors='coerce')

        # fill missing to_date with far future so comparisons are easy
        df['to_date'] = df['to_date'].fillna(pd.Timestamp("2100-01-01"))

        self.df = df

    def is_active(self, symbol, date):
        """
        True if symbol was part of Nifty50 on that date.
        """
        symbol = symbol.upper().strip()
        dt = pd.to_datetime(date)
        rows = self.df[self.df['symbol'].str.upper() == symbol]

        for _, row in rows.iterrows():
            frm = row['from_date']
            to  = row['to_date']
            if frm <= dt <= to:
                return True
        return False

    # alias for backward compatibility
    def is_member(self, symbol, date):
        return self.is_active(symbol, date)

    def get_active_symbols(self, on_date):
        """
        Returns list of all Nifty50 constituents on a given date.
        """
        dt = pd.to_datetime(on_date)
        mask = (self.df['from_date'] <= dt) & (self.df['to_date'] >= dt)
        return self.df.loc[mask,'symbol'].str.upper().unique().tolist()
