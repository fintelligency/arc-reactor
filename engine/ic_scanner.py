import pandas as pd
import datetime
from upload.gdrive_sync import append_to_gsheet
from utils.alerts import send_telegram_alert

def find_adaptive_ic_from_csv(csv_path):
    try:
        df_raw = pd.read_csv(csv_path, header=None)

        df_raw.columns = [
            "CE_OI", "CE_Chg_OI", "CE_Volume", "CE_IV", "CE_LTP", "CE_Chg",
            "CE_BidQty", "CE_Bid", "CE_Ask", "CE_AskQty",
            "Strike",
            "PE_BidQty", "PE_Bid", "PE_Ask", "PE_AskQty", "PE_Chg", "PE_LTP",
            "PE_IV", "PE_Volume", "PE_Chg_OI", "PE_OI"
        ]

        df = df_raw[["Strike", "CE_LTP", "PE_LTP"]].copy()
        df.columns = ["strike", "ce_ltp", "pe_ltp"]

        df = df.dropna()
        df["strike"] = pd.to_numeric(df["strike"], errors="coerce")
        df["ce_ltp"] = pd.to_numeric(df["ce_ltp"], errors="coerce")
        df["pe_ltp"] = pd.to_numeric(df["pe_ltp"], errors="coerce")
        df = df.dropna().sort_values(by="strike").reset_index(drop=True)

        ic_list = []

        for i in range(len(df)):
            for j in range(i + 4, len(df)):  # 800-point spread
                ce_sell = df.iloc[j]["strike"]
                pe_sell = df.iloc[i]["strike"]
                ce_ltp = df.iloc[j]["ce_ltp"]
                pe_ltp = df.iloc[i]["pe_ltp"]

                ce_buy_strike = ce_sell + 800
                pe_buy_strike = pe_sell - 800

                ce_buy_row = df[df["strike"] == ce_buy_strike]
                pe_buy_row = df[df["strike"] == pe_buy_strike]

                if ce_buy_row.empty or pe_buy_row.empty:
                    continue

                ce_buy = ce_buy_row["ce_ltp"].values[0]
                pe_buy = pe_buy_row["pe_ltp"].values[0]
                net_credit = ce_ltp + pe_ltp - ce_buy - pe_buy

                if net_credit <= 0:
                    continue

                ic_list.append({
                    "sell_pe": int(pe_sell),
                    "buy_pe": int(pe_buy_strike),
                    "sell_ce": int(ce_sell),
                    "buy_ce": int(ce_buy_strike),
                    "net_credit": round(net_credit, 2)
                })

        return sorted(ic_list, key=lambda x: -x["net_credit"])[:3]

    except Exception as e:
        raise Exception(f"❌ Error parsing CSV: {e}")

def log_and_alert_ic_candidates(ic_list, expiry):
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

    send_telegram_alert(f"🟢 *Top Adaptive IC Candidates ({expiry})*\n\n{msg}")
