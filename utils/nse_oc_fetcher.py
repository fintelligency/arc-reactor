import requests
import logging
import time
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
    "Connection": "keep-alive",
}

BASE_URL = "https://www.nseindia.com/api/option-chain-indices"


def fetch_nse_option_chain(symbol: str) -> List[Dict]:
    """
    Fetches the option chain data from NSE for NIFTY or BANKNIFTY.

    Args:
        symbol (str): Index symbol like 'NIFTY' or 'BANKNIFTY'

    Returns:
        List[Dict]: List of option data with CE/PE flattened
    """
    from requests.exceptions import RequestException, Timeout, HTTPError, ConnectionError

    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        # Warm up the session to obtain cookies
        session.get("https://www.nseindia.com", timeout=5)
        time.sleep(1)  # Delay to avoid getting blocked

        response = session.get(f"{BASE_URL}?symbol={symbol.upper()}", timeout=10)
        response.raise_for_status()

        data = response.json()
        records = data.get("records", {})
        oc_data = records.get("data", [])

        option_chain: List[Dict] = []

        for row in oc_data:
            strike_price = row.get("strikePrice")

            for opt_type in ["CE", "PE"]:
                if opt_type in row:
                    entry = row[opt_type]
                    entry["optionType"] = opt_type
                    entry["strikePrice"] = strike_price
                    option_chain.append(entry)

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
        logging.error(f"⚠️ Request exception occurred: {req_err}")
    except Exception as e:
        logging.exception("❌ Unexpected error while fetching NSE Option Chain")

    return []  # Ensure function always returns list for safe downstream processing
