# arc_reactor/engine/entry_signals.py

"""
Entry signals module for Arc Reactor hybrid strategy.

This function can be used in both live and backtest, as long as
- price_feed.get_price_row(symbol, date) returns dict with keys:
   { open, close, volume, rsi, vol_avg }
- gdrive_sync.get_open_positions(symbol) returns list of open position dicts
- dhan_orders.place_market_buy(symbol, qty) accepts market buy call

Zones implemented:
 - PP -> Direct buy
 - S1 -> Direct buy
 - S2 -> Buy if RSI < 40, bullish, volume > avg
 - S3 -> Buy if RSI < 35, bullish, volume > avg

Allocation per zone = config["ALLOCATION_PER_ZONE"] (default 25000)

"""

import logging
import numpy as np
from dataclasses import dataclass
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

@dataclass
class EntryResult:
    symbol: str
    zone: str
    action: str   # "BUY" or "SKIP"
    reason: str
    qty: Optional[int]
    price: Optional[float]
    capital: Optional[float]

def _compute_qty(price, allocation=25000.0):
    if price <= 0:
        return 0
    return int(allocation // price)

def _has_open_zone(symbol, zone, gdrive_sync):
    """
    Returns True if an open position already exists for this (symbol, zone)
    """
    positions = gdrive_sync.get_open_positions(symbol)
    for p in positions:
        if p.get("zone") == zone and p.get("status", "").lower() == "open":
            return True
    return False

def check_single_zone(symbol, zone, pivots, price_row, config, gdrive_sync, dhan_orders, alerts=None, date=None):
    """
    Core logic to check one zone of one symbol.
    If trade placed: returns EntryResult(action="BUY"), otherwise SKIP.
    """
    price = float(price_row['close'])
    bullish = price > price_row['open']
    rsi     = price_row.get('rsi', np.nan)
    vol     = price_row['volume']
    vol_avg = price_row.get('vol_avg', np.nan)

    alloc = config.get("ALLOCATION_PER_ZONE", 25000.0)

    # Check already open?
    if _has_open_zone(symbol, zone, gdrive_sync):
        return EntryResult(symbol, zone, "SKIP", "Zone allocation already open", None, None, None)

    # Determine trigger
    if zone == "PP":
        trigger = price <= pivots["P"]
    elif zone == "S1":
        trigger = price <= pivots["S1"]
    elif zone == "S2":
        trigger = price <= pivots["S2"]
    elif zone == "S3":
        trigger = price <= pivots["S3"]
    else:
        return EntryResult(symbol, zone, "SKIP", "Unknown zone", None, None, None)

    if not trigger:
        return EntryResult(symbol, zone, "SKIP", "Price not within zone", None, price, None)

    # Filter checks for S2/S3
    if zone == "S2":
        if (np.isnan(rsi) or rsi >= config.get("S2_RSI_MAX", 40)):
            return EntryResult(symbol, zone, "SKIP", "RSI filter fail", None, price, None)
        if not bullish:
            return EntryResult(symbol, zone, "SKIP", "Not bullish candle", None, price, None)
        if np.isnan(vol_avg) or not (vol > vol_avg):
            return EntryResult(symbol, zone, "SKIP", "Volume filter fail", None, price, None)

    if zone == "S3":
        if (np.isnan(rsi) or rsi >= config.get("S3_RSI_MAX", 35)):
            return EntryResult(symbol, zone, "SKIP", "RSI filter fail", None, price, None)
        if not bullish:
            return EntryResult(symbol, zone, "SKIP", "Not bullish candle", None, price, None)
        if np.isnan(vol_avg) or not (vol > vol_avg):
            return EntryResult(symbol, zone, "SKIP", "Volume filter fail", None, price, None)

    # Quantity
    qty = _compute_qty(price, alloc)
    if qty <= 0:
        return EntryResult(symbol, zone, "SKIP", "Qty <= 0", None, price, None)

    # Place order using injected dhan_orders
    try:
        resp = dhan_orders.place_market_buy(symbol, qty)
        filled_price = resp.get('filled_price', price) if isinstance(resp, dict) else price
    except Exception as e:
        logger.exception("Order failed: %s", e)
        return EntryResult(symbol, zone, "SKIP", "Order placement failed", None, None, None)

    # Log to sheet via gdrive_sync
    try:
        gdrive_sync.log_entry(symbol, zone, qty, filled_price, date, qty * filled_price)
    except Exception as e:
        logger.warning("GSheet log failed: %s", e)

    # Optional alert
    if alerts:
        msg = f"{symbol} BUY {zone} @ {filled_price:.2f} qty={qty}"
        try:
            alerts.send(msg)
        except Exception:
            pass

    return EntryResult(symbol, zone, "BUY", "Order placed", qty, filled_price, qty*filled_price)

def scan_multiple(symbols, pivots_map, price_feed, gdrive_sync, dhan_orders, config, alerts=None, date=None):
    """
    Scan multiple symbols in given order. Stops after one buy per symbol per day.
    """
    results = []
    zones = ["PP", "S1", "S2", "S3"]
    for sym in symbols:
        row = price_feed.get_price_row(sym, date)
        if not row:
            continue
        for zone in zones:
            res = check_single_zone(
                symbol=sym,
                zone=zone,
                pivots=pivots_map.get(sym, {}),
                price_row=row,
                config=config,
                gdrive_sync=gdrive_sync,
                dhan_orders=dhan_orders,
                alerts=alerts,
                date=date
            )
            results.append(res)
            # break if buy triggered for this symbol (one zone entry per day)
            if res.action == "BUY":
                break
    return results