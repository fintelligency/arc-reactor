import pandas as pd
import datetime
import yfinance as yf
from upload.gdrive_sync import append_to_gsheet
from utils.alerts import send_telegram_alert

def get_banknifty_spot():
    try:
        df = yf.download("^NSEBANK", period="1d", interval="1m")
        print(f"[DEBUG] Raw YF df shape: {df.shape}")

        if df.empty:
            raise ValueError("❌ Empty DataFrame returned from yfinance")

        df.columns = df.columns.str.strip()
        print(f"[DEBUG] Flattened Columns: {df.columns.tolist()}")

        if "Close" not in df.columns:
            raise ValueError("❌ 'Close' column not found in YF data")

        spot = df["Close"].iloc[-1]
        print(f"[DEBUG] Spot extracted: {spot}")
        return round(spot, 2)

    except Exception as e:
        print(f"[ICScanner] ⚠️ Failed to fetch spot price: {e}")
        return None


async def find_adaptive_ic_from_csv(csv_path):
    try:
        df_raw = pd.read_csv(csv_path, skiprows=1, thousands=",")
        df_raw.columns = df_raw.columns.str.strip()

        strike_col = next((col for col in df_raw.columns if "strike" in col.lower()), None)
        if not strike_col:
            raise ValueError("❌ Strike column not found.")

        strike_idx = list(df_raw.columns).index(strike_col)
        if strike_idx < 6 or strike_idx + 6 >= len(df_raw.columns):
            raise ValueError("❌ Column offset for LTPs is out of range.")

        print(f"[DEBUG] STRIKE column found: {strike_col} at index {strike_idx}")
        print(f"[DEBUG] Using CE_LTP @ {strike_idx - 6}, PE_LTP @ {strike_idx + 6}")

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
        max_credit_seen = 0
        total_checked = 0
        skip_reasons = []

        for i in range(len(df)):
            for j in range(i + 4, len(df)):
                total_checked += 1
                ce_sell = float(df.iloc[j]["strike"])
                pe_sell = float(df.iloc[i]["strike"])

                if pe_sell > spot or ce_sell < spot:
                    skip_reasons.append(f"{pe_sell}/{ce_sell} → One leg ITM")
                    continue

                ce_ltp = float(df.iloc[j]["ce_ltp"])
                pe_ltp = float(df.iloc[i]["pe_ltp"])

                ce_buy_strike = ce_sell + 800
                pe_buy_strike = pe_sell - 800

                if pe_buy_strike >= pe_sell or ce_buy_strike <= ce_sell:
                    skip_reasons.append(f"{pe_sell}/{ce_sell} → Hedge not OTM")
                    continue

                if pe_buy_strike == ce_buy_strike:
                    skip_reasons.append(f"{pe_sell}/{ce_sell} → Buy legs overlap")
                    continue

                ce_buy_row = df[df["strike"] == ce_buy_strike]
                pe_buy_row = df[df["strike"] == pe_buy_strike]

                if ce_buy_row.empty or pe_buy_row.empty:
                    skip_reasons.append(f"{pe_sell}/{ce_sell} → Hedge strikes missing")
                    continue

                try:
                    ce_buy = float(ce_buy_row["ce_ltp"].iloc[0])
                    pe_buy = float(pe_buy_row["pe_ltp"].iloc[0])
                except Exception as e:
                    skip_reasons.append(f"{pe_sell}/{ce_sell} → Error reading hedge LTP: {str(e)}")
                    continue

                net_credit = ce_ltp + pe_ltp - ce_buy - pe_buy
                if net_credit <= 0:
                    skip_reasons.append(f"{pe_sell}/{ce_sell} → Net credit ≤ 0")
                    continue

                max_credit_seen = max(max_credit_seen, net_credit)
                ic_list.append({
                    "sell_pe": int(pe_sell),
                    "buy_pe": int(pe_buy_strike),
                    "sell_ce": int(ce_sell),
                    "buy_ce": int(ce_buy_strike),
                    "net_credit": round(net_credit, 2)
                })

        summary = f"""\n🧪 *IC Scan Summary*\n• Total combos scanned: {total_checked}\n• Max credit observed: ₹{round(max_credit_seen, 2)}\n• Valid ICs found: {len(ic_list)}\n• Skipped examples:\n{chr(10).join(skip_reasons[:5]) if skip_reasons else 'None'}\n"""
        await send_telegram_alert(summary)
        return sorted(ic_list, key=lambda x: -x["net_credit"])[0:3]

    except Exception as e:
        raise ValueError(f"❌ Error parsing CSV: {e}")


async def log_and_alert_ic_candidates(ic_list, expiry):
    rows = []
    for ic in ic_list:
        row = {
            "Symbol": "BANKNIFTY",
            "Expiry": expiry,
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
    await send_telegram_alert(f"🟢 *Top Adaptive IC Candidates ({expiry})*\n\n{msg}")