"""Forecast-free strategy rules, shared by the backtest (explore.py) and the live paper trader.

Each rule sees one event snapshot at decision time and returns {ticker: side} with side in
{"buy_yes", "sell_yes"}. Orders rest at the bid (buy_yes) or the ask (sell_yes), maker style.
Snapshot: list of dicts with ticker, strike_type, floor, cap, bid, ask, mid, prev_mid (mid ~6h
earlier, or None), sorted from coldest to warmest bucket.
"""


def fav_longshot(snap):
    """Buy favorites 0.40-0.80, sell longshots 0.05-0.25 (favorite-longshot bias)."""
    out = {}
    for m in snap:
        if .40 <= m["mid"] < .80:
            out[m["ticker"]] = "buy_yes"
        elif .05 <= m["mid"] < .25:
            out[m["ticker"]] = "sell_yes"
    return out


def overround(snap):
    """When bucket mids sum well above 1, the excess sits mostly in longshots: sell them."""
    if sum(m["mid"] for m in snap) < 1.04:
        return {}
    return {m["ticker"]: "sell_yes" for m in snap if .05 <= m["mid"] < .30}


def tails(snap):
    """Sell the open-ended edge buckets ("X or above/below") when priced 0.05-0.30."""
    return {m["ticker"]: "sell_yes" for m in snap
            if m["strike_type"] in ("greater", "less") and .05 <= m["mid"] < .30}


def bump(snap):
    """Unimodality: a non-favorite bucket priced above both neighbours' average plus 5c is too rich."""
    out = {}
    top = max(range(len(snap)), key=lambda i: snap[i]["mid"])
    for i in range(1, len(snap) - 1):
        if abs(i - top) <= 1:
            continue
        nb = (snap[i - 1]["mid"] + snap[i + 1]["mid"]) / 2
        if snap[i]["mid"] > nb + .05 and snap[i]["mid"] >= .05:
            out[snap[i]["ticker"]] = "sell_yes"
    return out


def fade_move(snap):
    """Mean reversion: fade buckets whose mid moved 10c+ in the last 6h."""
    out = {}
    for m in snap:
        if m["prev_mid"] is None or not .05 <= m["mid"] <= .95:
            continue
        d = m["mid"] - m["prev_mid"]
        if d >= .10:
            out[m["ticker"]] = "sell_yes"
        elif d <= -.10:
            out[m["ticker"]] = "buy_yes"
    return out


def follow_move(snap):
    """Momentum: the opposite of fade_move."""
    flip = {"buy_yes": "sell_yes", "sell_yes": "buy_yes"}
    return {t: flip[s] for t, s in fade_move(snap).items()}


def sell_longshot(snap):
    """Sell YES priced 0.03-0.15. In econ.py backtests, buying YES under 10c lost ~2.5c per contract
    in every series (gas, TSA, ERCOT, S&P, Nasdaq), ~1.5c beyond the taker fee."""
    return {m["ticker"]: "sell_yes" for m in snap if .03 <= m["mid"] < .15}


RULES = {f.__name__: f for f in (fav_longshot, overround, tails, bump, fade_move, follow_move)}
# Ladder/non-weather series: bucket-structure rules (overround, bump, tails) don't apply.
ECON_RULES = {f.__name__: f for f in (sell_longshot,)}
# Same rule on a diversified non-sports basket (commodities, crypto, politics, mentions), scored separately.
DIV_RULES = {"sell_longshot_div": sell_longshot}
# Cross-series rules (rv_updown_*: updown quoted off the above-ladder) are logged by consistency.py log.
