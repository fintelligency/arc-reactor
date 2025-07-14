import pandas as pd
import datetime
import yfinance as yf
from upload.gdrive_sync import append_to_gsheet
from utils.alerts import send_telegram_alert

def get_banknifty_spot():
    try:
        df = yf.download("^NSEBANK", period="1d", interval="1m")
        if df.empty:
            raise ValueError("Empty spot data")
        return round(df['Close'].iloc[-1], 2)
    except Exception as e:
        print(f"[ICScanner] ⚠️ Failed to fetch spot price: {e}")
        return None

async def find_adaptive_ic_from_csv(csv_path):
    try:
        # 📥 Read CSV - Skip garbage title row, read clean header
        df_raw = pd.read_csv(csv_path, skiprows=1, thousands=",")

        # 🎯 Identify key columns dynamically
        strike_col = next((col for col in df_raw.columns if "strike" in col.lower()), None)
        ce_ltp_col = next((col for col in df_raw.columns if "call ltp" in col.lower()), None)
        pe_ltp_col = next((col for col in df_raw.columns if "put ltp" in col.lower()), None)

        if not strike_col or not ce_ltp_col or not pe_ltp_col:
            raise ValueError(f"❌ Required columns not found:\nStrike: {strike_col}\nCE LTP: {ce_ltp_col}\nPE LTP: {pe_ltp_col}")

        # 🧼 Extract only necessary columns
        df = df_raw[[strike_col, ce_ltp_col, pe_ltp_col]].copy()
        df.columns = ["strike", "ce_ltp", "pe_ltp"]

        # 🧹 Clean + Convert
        df.dropna(inplace=True)
        df["strike"] = pd.to_numeric(df["strike"].astype(str).str.replace(",", ""), errors="coerce")
        df["ce_ltp"] = pd.to_numeric(df["ce_ltp"].astype(str).str.replace(",", ""), errors="coerce")
        df["pe_ltp"] = pd.to_numeric(df["pe_ltp"].astype(str).str.replace(",", ""), errors="coerce")
        df.dropna(inplace=True)
        df.sort_values("strike", inplace=True)
        df.reset_index(drop=True, inplace=True)

        # 🚀 Fetch spot price
        spot = get_banknifty_spot()
        if spot is None:
            raise ValueError("Could not fetch BANKNIFTY spot price")

        ic_list = []
        max_credit_seen = 0
        total_checked = 0
        skip_reasons = []

        for i in range(len(df)):
            for j in range(i + 4, len(df)):  # Ensure ~800pt diff
                total_checked += 1
                ce_sell = float(df.iloc[j]["strike"])
                pe_sell = float(df.iloc[i]["strike"])

                # ⚠️ Reject ITM
                if pe_sell > spot or ce_sell < spot:
                    skip_reasons.append(f"{pe_sell}/{ce_sell} → One leg ITM")
                    continue

                ce_ltp = float(df.iloc[j]["ce_ltp"])
                pe_ltp = float(df.iloc[i]["pe_ltp"])

                ce_buy_strike = ce_sell + 800
                pe_buy_strike = pe_sell - 800

                # 🔍 Find hedge legs
                ce_buy_row = df[df["strike"] == ce_buy_strike]
                pe_buy_row = df[df["strike"] == pe_buy_strike]

                if ce_buy_row.empty or pe_buy_row.empty:
                    skip_reasons.append(f"{pe_sell}/{ce_sell} → Hedge strikes missing")
                    continue

                if len(ce_buy_row) != 1 or len(pe_buy_row) != 1:
                    skip_reasons.append(f"{pe_sell}/{ce_sell} → Duplicate hedge strike rows")
                    continue

                try:
                    ce_buy = float(ce_buy_row["ce_ltp"].values[0])
                    pe_buy = float(pe_buy_row["pe_ltp"].values[0])
                except (IndexError, ValueError, TypeError) as e:
                    skip_reasons.append(f"{pe_sell}/{ce_sell} → Error reading hedge LTP: {str(e)}")
                    continue

                net_credit = ce_ltp + pe_ltp - ce_buy - pe_buy
                if net_credit <= 0:
                    skip_reasons.append(f"{pe_sell}/{ce_sell} → Net credit ≤ 0")
                    continue

                # 📝 Log valid IC
                max_credit_seen = max(max_credit_seen, net_credit)
                ic_list.append({
                    "sell_pe": int(pe_sell),
                    "buy_pe": int(pe_buy_strike),
                    "sell_ce": int(ce_sell),
                    "buy_ce": int(ce_buy_strike),
                    "net_credit": round(net_credit, 2)
                })

        # 📊 Summary for Telegram
        summary = f"""🧪 *IC Scan Summary*
• Total combos scanned: {total_checked}
• Max credit observed: ₹{round(max_credit_seen, 2)}
• Valid ICs found: {len(ic_list)}
• Skipped examples:
{chr(10).join(skip_reasons[:5]) if skip_reasons else 'None'}
"""
        await send_telegram_alert(summary)
        return sorted(ic_list, key=lambda x: -x["net_credit"])[:3]

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

    # 🔔 Telegram Alert
    msg = "\n\n".join([
        f"*IC #{i+1}*\nPE: {ic['sell_pe']}/{ic['buy_pe']}\nCE: {ic['sell_ce']}/{ic['buy_ce']}\n💰 Credit: ₹{ic['net_credit']}"
        for i, ic in enumerate(ic_list)
    ])
    await send_telegram_alert(f"🟢 *Top Adaptive IC Candidates ({expiry})*\n\n{msg}")
