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

        df_ce = df_raw[[strike_col, df_raw.columns[strike_idx - 6]]].copy()
        df_pe = df_raw[[strike_col, df_raw.columns[strike_idx + 6]]].copy()

        df_ce.columns = ["strike", "ce_ltp"]
        df_pe.columns = ["strike", "pe_ltp"]

        df_ce["strike"] = pd.to_numeric(df_ce["strike"].astype(str).str.replace(",", ""), errors="coerce")
        df_ce["ce_ltp"] = pd.to_numeric(df_ce["ce_ltp"].astype(str).str.replace(",", ""), errors="coerce")
        df_pe["strike"] = pd.to_numeric(df_pe["strike"].astype(str).str.replace(",", ""), errors="coerce")
        df_pe["pe_ltp"] = pd.to_numeric(df_pe["pe_ltp"].astype(str).str.replace(",", ""), errors="coerce")

        df = pd.merge(df_ce, df_pe, on="strike", how="outer")
        df.dropna(subset=["strike"], inplace=True)
        df.sort_values("strike", inplace=True)
        df.reset_index(drop=True, inplace=True)

        spot = get_banknifty_spot()
        if spot is None:
            raise ValueError("❌ Could not fetch BANKNIFTY spot price")

        ic_list = []
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
            missing = []

            try:
                pe_sell_ltp = df.at[pe_sell, "pe_ltp"]
                if pe_sell_ltp == 0 or pd.isna(pe_sell_ltp):
                    missing.append(f"{pe_sell} PE Sell")

                pe_buy_ltp = df.at[pe_buy, "pe_ltp"]
                if pe_buy_ltp == 0 or pd.isna(pe_buy_ltp):
                    missing.append(f"{pe_buy} PE Buy")

                ce_sell_ltp = df.at[ce_sell, "ce_ltp"]
                if ce_sell_ltp == 0 or pd.isna(ce_sell_ltp):
                    missing.append(f"{ce_sell} CE Sell")

                ce_buy_ltp = df.at[ce_buy, "ce_ltp"]
                if ce_buy_ltp == 0 or pd.isna(ce_buy_ltp):
                    missing.append(f"{ce_buy} CE Buy")

            except KeyError as e:
                raise ValueError(f"❌ Locked IC failed: required strike {e.args[0]} not found in CSV.")

            if missing:
                raise ValueError(f"❌ Locked IC failed: illiquid/missing strikes: {', '.join(missing)}")

            net_credit = round(pe_sell_ltp + ce_sell_ltp - pe_buy_ltp - ce_buy_ltp, 2)
            ic_list.append({**legs, "net_credit": net_credit, "expiry": expiry})

            await send_telegram_alert(
                f"📦 *Locked IC Strategy ({expiry})*\nPE: {pe_sell}/{pe_buy}\nCE: {ce_sell}/{ce_buy}\n💰 Credit: ₹{net_credit}"
            )
            return ic_list

        # --- Adaptive scan mode ---
        for i in range(len(df)):
            for j in range(i + 4, len(df)):
                total_checked += 1
                ce_sell = float(df.iloc[j]["strike"])
                pe_sell = float(df.iloc[i]["strike"])

                if pe_sell > spot or ce_sell < spot:
                    continue

                ce_ltp = df.iloc[j].get("ce_ltp", None)
                pe_ltp = df.iloc[i].get("pe_ltp", None)

                ce_buy_strike = ce_sell + 800
                pe_buy_strike = pe_sell - 800

                ce_buy_row = df[df["strike"] == ce_buy_strike]
                pe_buy_row = df[df["strike"] == pe_buy_strike]

                if ce_buy_row.empty or pe_buy_row.empty:
                    continue

                ce_buy = ce_buy_row.iloc[0].get("ce_ltp", None)
                pe_buy = pe_buy_row.iloc[0].get("pe_ltp", None)

                if any(pd.isna(x) or x == 0 for x in [ce_ltp, pe_ltp, ce_buy, pe_buy]):
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