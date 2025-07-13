import pandas as pd
import datetime
from utils.alerts import send_telegram_alert
from upload.gdrive_sync import append_to_gsheet
import json

# Load optional config for scoring weights
try:
    with open("config/ic_settings.json") as f:
        IC_CONFIG = json.load(f)
except:
    IC_CONFIG = {
        "wing_width": 800,
        "max_wing_width": 1000
    }

def parse_float(val):
    try:
        return float(str(val).replace(",", "").strip())
    except:
        return None

def find_adaptive_ic_from_csv(csv_path):
    df_raw = pd.read_csv(csv_path, skiprows=1)
    df_raw = df_raw.loc[:, ~df_raw.columns.str.contains('^Unnamed')]
    df_raw.columns = df_raw.columns.str.strip()

    # Heuristic matching for required columns
    def get_column(name_hint):
        return next((col for col in df_raw.columns if name_hint.lower() in col.lower()), None)

    strike_col = get_column("strike")
    ce_ltp_col = get_column("ce ltp") or get_column("ltp")
    ce_oi_col = get_column("ce oi") or get_column("oi")
    pe_ltp_col = get_column("pe ltp") or get_column("ltp.1")
    pe_oi_col = get_column("pe oi") or get_column("oi.1")

    if not all([strike_col, ce_ltp_col, ce_oi_col, pe_ltp_col, pe_oi_col]):
        raise ValueError("❌ Required columns not found in uploaded file.")

    df = pd.DataFrame({
        'strike': df_raw[strike_col].apply(parse_float),
        'ce_ltp': df_raw[ce_ltp_col].apply(parse_float),
        'ce_oi': df_raw[ce_oi_col].apply(parse_float),
        'pe_ltp': df_raw[pe_ltp_col].apply(parse_float),
        'pe_oi': df_raw[pe_oi_col].apply(parse_float),
    }).dropna().reset_index(drop=True)

    spot_guess = df['strike'].mean()

    ics = []
    for i, ce_row in df.iterrows():
        for j, pe_row in df.iterrows():
            ce_strike = ce_row['strike']
            pe_strike = pe_row['strike']
            wing = ce_strike - pe_strike

            if wing < IC_CONFIG["wing_width"] or wing > IC_CONFIG["max_wing_width"]:
                continue

            buy_ce = df[df['strike'] == ce_strike + IC_CONFIG['wing_width']]
            buy_pe = df[df['strike'] == pe_strike - IC_CONFIG['wing_width']]
            if buy_ce.empty or buy_pe.empty:
                continue

            ce_buy = buy_ce.iloc[0]['ce_ltp']
            pe_buy = buy_pe.iloc[0]['pe_ltp']
            credit = ce_row['ce_ltp'] + pe_row['pe_ltp'] - ce_buy - pe_buy

            score = (
                credit * 0.4
                + (100 - (ce_buy + pe_buy)) * 0.2
                + (wing * 0.2)
                + (min(ce_row['ce_oi'], pe_row['pe_oi']) / 10000) * 0.2
            )

            ics.append({
                "spot": round(spot_guess),
                "sell_ce": ce_strike,
                "buy_ce": ce_strike + IC_CONFIG['wing_width'],
                "sell_pe": pe_strike,
                "buy_pe": pe_strike - IC_CONFIG['wing_width'],
                "net_credit": round(credit, 2),
                "score": round(score, 2),
            })

    return sorted(ics, key=lambda x: -x["score"])[:3]

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

    message = "\n\n".join([
        f"*IC #{i+1}*\nPE: {r['Sell PE']}/{r['Buy PE']}\nCE: {r['Sell CE']}/{r['Buy CE']}\n💰 Credit: ₹{r['Net Credit']}"
        for i, r in enumerate(rows)
    ])
    send_telegram_alert(f"🟩 *Top IC Candidates ({expiry})*\n\n{message}")
