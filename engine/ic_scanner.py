# engine/ic_scanner.py

import pandas as pd
import datetime
from upload.gdrive_sync import append_to_gsheet
from utils.alerts import send_telegram_alert

async def find_adaptive_ic_from_csv(csv_path):
    try:
        # Load CSV skipping header noise
        df_raw = pd.read_csv(csv_path, skiprows=1)

        # Map fixed column indexes for NSE format
        strike_col = df_raw.columns[10]
        ce_ltp_col = df_raw.columns[4]
        pe_ltp_col = df_raw.columns[16]

        # Extract and clean necessary columns
        df = df_raw[[strike_col, ce_ltp_col, pe_ltp_col]].copy()
        df.columns = ["strike", "ce_ltp", "pe_ltp"]

        # Clean commas and convert to numbers
        df["strike"] = pd.to_numeric(df["strike"].astype(str).str.replace(",", ""), errors="coerce")
        df["ce_ltp"] = pd.to_numeric(df["ce_ltp"].astype(str).str.replace(",", ""), errors="coerce")
        df["pe_ltp"] = pd.to_numeric(df["pe_ltp"].astype(str).str.replace(",", ""), errors="coerce")

        df.dropna(inplace=True)
        df.sort_values("strike", inplace=True)
        df.reset_index(drop=True, inplace=True)

        print(f"[ICScanner] 🔍 Cleaned DataFrame:\n\n{df.head()}")
        print(f"[ICScanner] ✅ Rows after cleanup: {len(df)}")

        ic_list = []
        max_credit_seen = 0
        total_checked = 0
        skip_reasons = []

        for i in range(len(df)):
            for j in range(i + 4, len(df)):  # Ensure minimum spread
                total_checked += 1
                ce_sell = df.iloc[j]["strike"]
                pe_sell = df.iloc[i]["strike"]
                ce_ltp = df.iloc[j]["ce_ltp"]
                pe_ltp = df.iloc[i]["pe_ltp"]

                ce_buy_strike = ce_sell + 800
                pe_buy_strike = pe_sell - 800

                ce_buy_row = df[df["strike"] == ce_buy_strike]
                pe_buy_row = df[df["strike"] == pe_buy_strike]

                if ce_buy_row.empty or pe_buy_row.empty:
                    skip_reasons.append(f"{pe_sell}/{ce_sell} → Hedge strikes missing")
                    continue

                ce_buy = ce_buy_row["ce_ltp"].values[0]
                pe_buy = pe_buy_row["pe_ltp"].values[0]
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

    msg = "\n\n".join([
        f"*IC #{i+1}*\nPE: {ic['sell_pe']}/{ic['buy_pe']}\nCE: {ic['sell_ce']}/{ic['buy_ce']}\n💰 Credit: ₹{ic['net_credit']}"
        for i, ic in enumerate(ic_list)
    ])

    await send_telegram_alert(f"🟢 *Top Adaptive IC Candidates ({expiry})*\n\n{msg}")