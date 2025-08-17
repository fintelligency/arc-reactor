# arc_reactor/utils/nifty_manager.py

"""
Utility class to manage Nifty50 membership based on a CSV file.
CSV MUST have columns: Symbol, from_date, to_date
Dates should be in DD-MMM-YY or YYYY-MM-DD.
"""

import pandas as pd

class NiftyManager:
    def __init__(self, csv_path="arc_reactor/data/nifty50_membership.csv"):
        # Load CSV
        self.df = pd.read_csv(csv_path)
        # Normalize column names to lowercase
        self.df.columns = [c.strip().lower() for c in self.df.columns]

        # Ensure correct column names
        required_cols = {"symbol", "from_date", "to_date"}
        if not required_cols.issubset(set(self.df.columns)):
            raise ValueError(f"File {csv_path} must contain columns: {required_cols}")

        # Parse dates
        self.df['from_date'] = pd.to_datetime(self.df['from_date'], errors='coerce')
        self.df['to_date']   = pd.to_datetime(self.df['to_date'],   errors='coerce')

    def get_active_symbols(self, on_date):
        """
        Return a list of symbols that were part of Nifty50 on on_date.
        on_date: string or datetime
        """
        if isinstance(on_date, str):
            dt = pd.to_datetime(on_date)
        else:
            dt = pd.to_datetime(on_date)

        mask = (
                (self.df['from_date'] <= dt) &
                (self.df['to_date'].isna() | (self.df['to_date'] >= dt))
        )
        return self.df.loc[mask,'symbol'].unique().tolist()

    def get_symbols_on_date(self, dt):
        """
        Returns the list of Nifty50 symbols active on the given date.
        dt: datetime.date or datetime-like
        """
        mask = (
                (self.df['from_date'] <= dt) &
                ((self.df['to_date'].isna()) | (self.df['to_date'] >= dt))
        )
        return self.df.loc[mask, 'symbol'].unique().tolist()

    def is_active(self, symbol, on_date):
        """
        Returns True if the given symbol was part of the Nifty50 on that date.
        """
        if isinstance(on_date, str):
            dt = pd.to_datetime(on_date)
        else:
            dt = pd.to_datetime(on_date)

        symbol = symbol.strip().upper()
        rows = self.df[self.df['symbol'].str.upper() == symbol]

        if rows.empty:
            return False

        for _, row in rows.iterrows():
            frm = row['from_date']
            to  = row['to_date']
            # if from_date is NaT, assume always active until to_date
            if pd.isna(frm) or frm <= dt:
                if pd.isna(to) or dt <= to:
                    return True

        return False


# Example usage:
# if __name__ == "__main__":
#     nm = NiftyManager("arc_reactor/data/nifty50_membership.csv")
#     print(nm.get_active_symbols("2018-04-01"))
#     print(nm.is_active("RELIANCE", "2015-01-01"))
