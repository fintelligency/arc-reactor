import requests
import pandas as pd
import datetime
import asyncio
from upload.gdrive_sync import append_to_gsheet
from utils.alerts import send_telegram_alert

NSE_BASE = "https://www.nseindia.com"
OC_URL = "https://www.nseindia.com/api/option-chain-indices?symbol=BANKNIFTY"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}

def fetch_option_chain():
    session = requests.Session()
    session.get(NSE_BASE, headers=HEADERS)
    response = session.get(OC_URL, headers=HEADERS)
    data = response.json()
    return data

def parse_option_chain(data):
    records = data['records']['data']
    spot = float(data['records']['underlyingValue'])
    expiry = data['records']['expiryDates'][0]  # Monthly expiry
    ce_list = []
    pe_list = []

    for r in records:
        strike = r.get("strikePrice")
        ce = r.get("CE")
        pe = r.get("PE")
        if ce and ce['expiryDate'] == expiry:
            ce_list.append({"strike": strike, "ltp": ce['lastPrice'], "oi": ce['openInterest']})
        if pe and pe['expiryDate'] == expiry:
            pe_list.append({"strike": strike, "ltp": pe['lastPrice'], "oi": pe['openInterest']})

    df_ce = pd.DataFrame(ce_list).dropna()
    df_pe = pd.DataFrame(pe_list).dropna()
    return spot, expiry, df_ce, df_pe

def find_valid_ic(spot, df_ce, df_pe):
    valid_ics = []
    ce_candidates = df_ce[(df_ce['ltp'] >= 650) & (df_ce['oi'] > 10000)]
    pe_candidates = df_pe[(df_pe['ltp'] >= 650) & (df_pe['oi'] > 10000)]

    for _, ce_row in ce_candidates.iterrows():
        for _, pe_row in pe_candidates.iterrows():
            ce_strike = ce_row['strike']
            pe_strike = pe_row['strike']

            if ce_strike - pe_strike < 1600:  # Wing width 800 each side
                continue

            buy_ce = df_ce[df_ce['strike'] == ce_strike + 800]
            buy_pe = df_pe[df_pe['strike'] == pe_strike - 800]

            if buy_ce.empty or buy_pe.empty:
                continue

            ce_sell = ce_row['ltp']
            pe_sell = pe_row['ltp']
            ce_buy = float(buy_ce['ltp'].values[0])
            pe_buy = float(buy_pe['ltp'].values[0])

            net_credit = ce_sell + pe_sell - ce_buy - pe_buy

            if ce_buy <= 250 and pe_buy <= 250 and net_credit >= 800:
                if pe_strike <= spot * 0.97 and ce_strike >= spot * 1.03:
                    valid_ics.append({
                        "spot": spot,
                        "sell_pe": pe_strike,
                        "buy_pe": pe_strike - 800,
                        "sell_ce": ce_strike,
                        "buy_ce": ce_strike + 800,
                        "net_credit": round(net_credit, 2)
                    })
    return sorted(valid_ics, key=lambda x: -x['net_credit'])[:3]

def log_and_alert_ic(ic_list, expiry):
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
    asyncio.create_task(send_telegram_alert(f"🟩 *Top IC Candidates ({expiry})*\n\n{message}"))

async def run_ic_entry_scan():
    try:
        data = fetch_option_chain()
        spot, expiry, df_ce, df_pe = parse_option_chain(data)
        ic_list = find_valid_ic(spot, df_ce, df_pe)
        if ic_list:
            log_and_alert_ic(ic_list, expiry)
        else:
            await send_telegram_alert("⚠️ No valid Iron Condor found today.")
    except Exception as e:
        print(f"[ICEntry] ❌ Error: {e}")
        await send_telegram_alert(f"❌ IC Scanner failed: {e}")

if __name__ == "__main__":
    asyncio.run(run_ic_entry_scan())
