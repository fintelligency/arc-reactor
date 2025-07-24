import pandas as pd
import datetime
import yfinance as yf
import re
import os
from upload.gdrive_sync import append_to_gsheet, get_config_dict
from utils.alerts import send_telegram_alert

STRIKE_INTERVAL = 100
MARGIN_REQUIREMENT = 160000

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
    base = os.path.basename(filename).split('.')[0]
    match = re.search(r'(\d{1,2})-([A-Za-z]{3})-(\d{4})', base)
    try:
        expiry = datetime.datetime.strptime("-".join(match.groups()), "%d-%b-%Y") if match else datetime.datetime.now()
        return expiry.strftime("%d-%b-%Y")
    except (ValueError, AttributeError) as e:
        print(f"[Parser] ⚠️ Failed to parse expiry: {e}")
        return datetime.datetime.now().strftime("%d-%b-%Y")

def round_to_nearest(x, base=STRIKE_INTERVAL):
    return base * round(x / base)


async def find_adaptive_ic_from_csv(csv_path):
    config = get_config_dict()

    min_wing_width = int(config.get("min_wing_width", 800))
    min_net_credit = int(config.get("min_net_credit", 300))
    min_spot_diff = int(config.get("min_spot_diff", 1000))
    top_n = int(config.get("top_n_strategies", 3))

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
            raise ValueError("❌ Could not fetch spot price")

        ic_list = []
        total_checked = 0
        max_credit_seen = 0

        for i in range(len(df)):
            for j in range(i + 4, len(df)):
                total_checked += 1
                ce_sell, pe_sell = float(df.iloc[j]["strike"]), float(df.iloc[i]["strike"])
                if pe_sell > spot or ce_sell < spot:
                    continue

                if (spot - pe_sell) < min_spot_diff or (ce_sell - spot) < min_spot_diff:
                    continue

                ce_ltp = df.iloc[j].get("ce_ltp")
                pe_ltp = df.iloc[i].get("pe_ltp")

                ce_buy_strike = ce_sell + min_wing_width
                pe_buy_strike = pe_sell - min_wing_width

                ce_buy = df[df["strike"] == ce_buy_strike]["ce_ltp"].values
                pe_buy = df[df["strike"] == pe_buy_strike]["pe_ltp"].values

                if not ce_buy.size or not pe_buy.size:
                    continue

                ce_buy, pe_buy = ce_buy[0], pe_buy[0]
                if any(pd.isna(x) or x == 0 for x in [ce_ltp, pe_ltp, ce_buy, pe_buy]):
                    continue

                net_credit = ce_ltp + pe_ltp - ce_buy - pe_buy
                if net_credit < min_net_credit:
                    continue

                max_credit_seen = max(max_credit_seen, net_credit)
                ic_list.append({
                    "sell_pe": int(pe_sell), "buy_pe": int(pe_buy_strike),
                    "sell_ce": int(ce_sell), "buy_ce": int(ce_buy_strike),
                    "net_credit": round(net_credit, 2), "expiry": expiry
                })

        summary = f"""
🧪 *IC Scan Summary*
• Total combos scanned: {total_checked}
• Max credit observed: ₹{round(max_credit_seen, 2)}
• Valid ICs found: {len(ic_list)}
"""
        await send_telegram_alert(summary)
        return sorted(ic_list, key=lambda x: -x["net_credit"])[:top_n]

    except Exception as e:
        raise ValueError(f"❌ Error parsing CSV: {e}")


async def log_and_alert_ic_candidates(ic_list):
    if not ic_list:
        return

    config = get_config_dict()
    output_sheet = config.get("output_sheet", "IC_Trades")
    symbol = config.get("symbol", "BANKNIFTY")

    rows = []
    for ic in ic_list:
        rows.append({
            "Symbol": symbol,
            "Expiry": ic["expiry"],
            "Sell PE": ic['sell_pe'],
            "Buy PE": ic['buy_pe'],
            "Sell CE": ic['sell_ce'],
            "Buy CE": ic['buy_ce'],
            "Net Credit": ic['net_credit'],
            "Margin": MARGIN_REQUIREMENT,
            "Status": "New",
            "Timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    append_to_gsheet(rows, sheet_name=output_sheet)

    msg = "\n\n".join([
        f"*IC #{i+1}*\nPE: {ic['sell_pe']}/{ic['buy_pe']}\nCE: {ic['sell_ce']}/{ic['buy_ce']}\n💰 Credit: ₹{ic['net_credit']}"
        for i, ic in enumerate(ic_list)
    ])
    await send_telegram_alert(f"🟢 *Top IC Candidates ({ic_list[0]['expiry']})*\n\n{msg}")
