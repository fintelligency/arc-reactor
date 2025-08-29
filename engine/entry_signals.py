# entry_signals.py
import pandas as pd


class EntryResult:
    def __init__(self, symbol, zone, action, message, qty=None, price=None, value=None):
        self.symbol = symbol
        self.zone = zone
        self.action = action
        self.message = message
        self.qty = qty
        self.price = price
        self.value = value


def check_single_zone(
    symbol,
    zone,
    pivots,
    price_row,
    config,
    date,
    current_year,
    active_positions,
):
    low_px = price_row.get("low")
    if low_px is None:
        return None

    # Ensure symbol tracking structure
    if symbol not in active_positions:
        active_positions[symbol] = {}

    # 🚫 Block if already an active trade for (zone, year)
    if active_positions[symbol].get((zone, current_year)):
        return None

    # 🚫 Block if trade already taken today for same (zone, date)
    if active_positions[symbol].get((zone, date)):
        return None

    zone_price = pivots.get(zone.upper())
    if zone_price is None:
        return None

    # ✅ BUY trigger at LOW <= zone price
    if low_px <= zone_price:
        qty = int(config["ALLOCATION_PER_ZONE"] // zone_price)
        filled_price = zone_price

        # Mark this zone slot as used for this year
        active_positions[symbol][(zone, current_year)] = True
        # Also mark for this date → avoids duplicate same-day entries
        active_positions[symbol][(zone, date)] = True

        return EntryResult(
            symbol,
            zone,
            "BUY",
            "Order placed",
            qty,
            filled_price,
            qty * filled_price,
        )

    return None


def scan_multiple(symbols, pivots_map, price_feed, config, date, current_year, active_positions):
    results = []
    for sym in symbols:
        price_row = price_feed.get_price_row(sym, date)
        if not price_row:
            continue

        for zone in ["PP", "S1", "S2", "S3"]:
            res = check_single_zone(
                symbol=sym,
                zone=zone,
                pivots=pivots_map.get(sym, {}),
                price_row=price_row,
                config=config,
                date=date,
                current_year=current_year,
                active_positions=active_positions,
            )
            if res:
                results.append(res)
    return results
