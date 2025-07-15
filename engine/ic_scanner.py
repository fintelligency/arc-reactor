import pandas as pd
import datetime
import yfinance as yf
import re
from upload.gdrive_sync import append_to_gsheet
from utils.alerts import send_telegram_alert


def get_banknifty_spot():
    try:
        df = yf.download("^NSEBANK", period="1d", interval="1m", auto_adjust=False)
        if isinstance(df.columns, pd.MultiIndex):
            if ('Close', '^NSEBANK') in df.columns:
                close_series = df[('Close', '^NSEBANK')]
            else:
                raise ValueError("❌ 'Close' column not found in MultiIndex")
        else:
            if "Close" in df.columns:
                close_series = df["Close"]
            else:
                raise ValueError("❌ 'Close' column not found in flat index")

        spot = close_series.dropna().iloc[-1]
        return round(spot, 2)

    except Exception as e:
        print(f"[ICScanner] ⚠️ Failed to fetch spot price: {e}")
        return None


def extract_expiry_from_filename(filename: str) -> str:
    import os
    base = os.path.basename(filename).split('.')[0]
    match = re.search(r'(\d{1,2})-([A-Za-z]{3})-(\d{4})', base)
    if not match:
        return datetime.datetime.now().strftime("%d-%b-%Y")
    day, mon, year = match.groups()
    try:
        expiry = datetime.datetime.strptime(f"{day}-{mon}-{year}", "%d-%b-%Y")
        return expiry.strftime("%d-%b-%Y")
    except:
        return datetime.datetime.now().strftime("%d-%b-%Y")


def round_to_nearest(x, base=100):
    return base * round(x / base)


async def find_adaptive_ic_from_csv(csv_path, locked_mode=False):
    try:
        expiry = extract_expiry_from_filename(csv_path)

        df_raw = pd.read_csv(csv_path, skiprows=1, thousands=",")
        df_raw.columns = df_raw.columns.str.strip()

        strike_col = next((col for col in df_raw.columns if "strike" in col.lower()), None)
        if not strike_col:
            raise ValueError("❌ Strike column not found.")

        strike_idx = list(df_raw.columns).index(strike_col)
        if strike_idx < 6 or strike_idx + 6 >= len(df_raw.columns):
            raise ValueError("❌ Column offset for LTPs is out of range.")

        df = pd.DataFrame({
            "strike": df_raw.iloc[:, strike_idx],
            "ce_ltp": df_raw.iloc[:, strike_idx - 6],
            "pe_ltp": df_raw.iloc[:, strike_idx + 6],
        })

        df.dropna(inplace=True)
        df["strike"] = pd.to_numeric(df["strike"].astype(str).str.replace(",", ""), errors="coerce")
        df["ce_ltp"] = pd.to_numeric(df["ce_ltp"].astype(str).str.replace(",", ""), errors="coerce")
        df["pe_ltp"] = pd.to_numeric(df["pe_ltp"].astype(str).str.replace(",", ""), errors="coerce")
        df.dropna(inplace=True)
        df.sort_values("strike", inplace=True)
        df.reset_index(drop=True, inplace=True)

        spot = get_banknifty_spot()
        if spot is None:
            raise ValueError("❌ Could not fetch BANKNIFTY spot price")

        ic_list = []
        skip_reasons = []
        max_credit_seen = 0
        total_checked = 0

        if locked_mode:
            pe_sell = round_to_nearest(spot - 1500, 500)
            pe_buy = pe_sell - 1000
            ce_sell = round_to_nearest(spot + 1500, 500)
            ce_buy = ce_sell + 1000

            legs = {
                "sell_pe": pe_sell,
                "buy_pe": pe_buy,
                "sell_ce": ce_sell,
                "buy_ce": ce_buy,
            }

            df.set_index("strike", inplace=True)

            try:
                pe_sell_ltp = df.at[pe_sell, "pe_ltp"]
                pe_buy_ltp = df.at[pe_buy, "pe_ltp"]
                ce_sell_ltp = df.at[ce_sell, "ce_ltp"]
                ce_buy_ltp = df.at[ce_buy, "ce_ltp"]
            except:
                raise ValueError("❌ One of the required strikes is missing in option chain.")

            net_credit = round(pe_sell_ltp + ce_sell_ltp - pe_buy_ltp - ce_buy_ltp, 2)

            ic_list.append({
                **legs,
                "net_credit": net_credit,
                "expiry": expiry
            })

            await send_telegram_alert(
                f"📦 *Locked IC Strategy ({expiry})*\nPE: {pe_sell}/{pe_buy}\nCE: {ce_sell}/{ce_buy}\n💰 Credit: ₹{net_credit}"
            )
            return ic_list

        else:
            for i in range(len(df)):
                for j in range(i + 4, len(df)):
                    total_checked += 1
                    ce_sell = float(df.iloc[j]["strike"])
                    pe_sell = float(df.iloc[i]["strike"])

                    if pe_sell > spot or ce_sell < spot:
                        continue

                    ce_ltp = float(df.iloc[j]["ce_ltp"])
                    pe_ltp = float(df.iloc[i]["pe_ltp"])

                    ce_buy_strike = ce_sell + 800
                    pe_buy_strike = pe_sell - 800

                    if pe_buy_strike >= pe_sell or ce_buy_strike <= ce_sell:
                        continue

                    if pe_buy_strike == ce_buy_strike:
                        continue

                    ce_buy_row = df[df["strike"] == ce_buy_strike]
                    pe_buy_row = df[df["strike"] == pe_buy_strike]

                    if ce_buy_row.empty or pe_buy_row.empty:
                        continue

                    try:
                        ce_buy = float(ce_buy_row["ce_ltp"].iloc[0])
                        pe_buy = float(pe_buy_row["pe_ltp"].iloc[0])
                    except:
                        continue

                    net_credit = ce_ltp + pe_ltp - ce_buy - pe_buy
                    if net_credit <= 0:
                        continue

                    max_credit_seen = max(max_credit_seen, net_credit)
                    ic_list.append({
                        "sell_pe": int(pe_sell),
                        "buy_pe": int(pe_buy_strike),
                        "sell_ce": int(ce_sell),
                        "buy_ce": int(ce_buy_strike),
                        "net_credit": round(net_credit, 2),
                        "expiry": expiry
                    })

            summary = f"""\n🧪 *IC Scan Summary*\n• Total combos scanned: {total_checked}\n• Max credit observed: ₹{round(max_credit_seen, 2)}\n• Valid ICs found: {len(ic_list)}\n"""
            await send_telegram_alert(summary)
            return sorted(ic_list, key=lambda x: -x["net_credit"])[:3]

    except Exception as e:
        raise ValueError(f"❌ Error parsing CSV: {e}")


async def log_and_alert_ic_candidates(ic_list):
    if not ic_list:
        return

    rows = []
    for ic in ic_list:
        row = {
            "Symbol": "BANKNIFTY",
            "Expiry": ic["expiry"],
            "Sell PE": ic['sell_pe'],
            "Buy PE": ic['buy_pe'],
            "Sell CE": ic['sell_ce'],
            "Buy CE": ic['buy_ce'],
            "Net Credit": ic['net_credit'],
            "Margin": 160000,
            "Status": "New",
            "Timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        rows.append(row)

    append_to_gsheet(rows, sheet_name="ic_trades")

    msg = "\n\n".join([
        f"*IC #{i+1}*\nPE: {ic['sell_pe']}/{ic['buy_pe']}\nCE: {ic['sell_ce']}/{ic['buy_ce']}\n💰 Credit: ₹{ic['net_credit']}"
        for i, ic in enumerate(ic_list)
    ])
    expiry_str = ic_list[0]["expiry"]
    await send_telegram_alert(f"🟢 *Top IC Candidates ({expiry_str})*\n\n{msg}")