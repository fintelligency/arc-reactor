import requests
import logging
from typing import List, Dict

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/114.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com",
}

BASE_URL = "https://www.nseindia.com/api/option-chain-indices"

def fetch_nse_option_chain(symbol: str) -> List[Dict]:
    """
    Fetch the option chain for NIFTY or BANKNIFTY from NSE website.

    Args:
        symbol (str): 'NIFTY' or 'BANKNIFTY'

    Returns:
        List[Dict]: List of option chain data rows
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    from requests.exceptions import RequestException, Timeout, HTTPError, ConnectionError

    try:
        # Warm-up request to get cookies
        _ = session.get("https://www.nseindia.com", timeout=5)

        # Actual request
        url = f"{BASE_URL}?symbol={symbol.upper()}"
        response = session.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()
        records = data.get("records", {})
        oc_data = records.get("data", [])

        # Flatten CE + PE per strike
        option_chain = []
        for row in oc_data:
            strike_price = row.get("strikePrice")

            if "CE" in row:
                ce = row["CE"]
                ce["optionType"] = "CE"
                ce["strikePrice"] = strike_price
                option_chain.append(ce)

            if "PE" in row:
                pe = row["PE"]
                pe["optionType"] = "PE"
                pe["strikePrice"] = strike_price
                option_chain.append(pe)

        return option_chain

    except (ConnectionError, Timeout) as net_err:
        logging.error(f"🌐 Network error while fetching NSE data: {net_err}")
    except HTTPError as http_err:
        logging.error(f"📶 HTTP error while fetching NSE data: {http_err}")
    except ValueError as val_err:
        logging.error(f"❗ JSON parsing error: {val_err}")
    except KeyError as key_err:
        logging.error(f"🔍 Missing expected key in NSE response: {key_err}")
    except RequestException as req_err:
        logging.error(f"⚠️ General request exception: {req_err}")

    # ✅ Ensure a fallback return to satisfy type checker
    return []