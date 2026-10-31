"""Favorite-longshot rule executed as a resting (maker) order, with conservative fills.

At H hours before close, for each market by mid price:
  favorite (0.40 <= mid < 0.80): rest a buy-YES at the bid
  longshot (0.05 <= mid < 0.25): rest a sell-YES at the ask (i.e. buy NO at 1 - ask)
Filled only if a later trade within WINDOW hours prints strictly through the order price
(trade low < bid, or trade high > ask), which builds in adverse selection.
P&L after Kalshi maker fee. Event-clustered CIs, split by first/second half of dates.
Usage: python3 maker.py
"""
import collections, json, math, os
from datetime import datetime
from analyze import rd, DATA
from intraday import edate, boot, mean

WINDOW = 6


def f(x):
    return float(x) if x not in (None, "") else None


def mfee(p):
    return math.ceil(0.0175 * p * (1 - p) * 100) / 100


def main():
    markets = rd("markets.csv")
    dates = sorted({edate(m["event"]) for m in markets})
    split = dates[len(dates) // 2]
    for H in (36, 30, 24, 18):
        out = collections.defaultdict(list)
        fills = collections.Counter()
        for m in markets:
            cs = json.load(open(os.path.join(DATA, "cache", m["ticker"] + ".json")))
            close = datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).timestamp()
            t0 = close - H * 3600
            before = [c for c in cs if c["end_period_ts"] <= t0]
            after = [c for c in cs if t0 < c["end_period_ts"] <= t0 + WINDOW * 3600]
            if not before:
                continue
            c = before[-1]
            b, a = f(c["yes_bid"]["close_dollars"]), f(c["yes_ask"]["close_dollars"])
            if b is None or a is None or not 0 < b < a < 1:
                continue
            mid, y = (a + b) / 2, 1.0 if m["result"] == "yes" else 0.0
            lows = [f(x["price"].get("low_dollars")) for x in after]
            highs = [f(x["price"].get("high_dollars")) for x in after]
            half = "A" if edate(m["event"]) < split else "B"
            if .40 <= mid < .80:
                k = "favorite buy@bid"
                fills[k, "tried"] += 1
                if any(l is not None and l < b for l in lows):
                    fills[k, "filled"] += 1
                    out[k, half].append((m["event"], y - b - mfee(b)))
            elif .05 <= mid < .25:
                k = "longshot sell@ask"
                fills[k, "tried"] += 1
                if any(h is not None and h > a for h in highs):
                    fills[k, "filled"] += 1
                    out[k, half].append((m["event"], a - y - mfee(1 - a)))
        print(f"--- {H}h before close, fill window {WINDOW}h")
        for k in ("favorite buy@bid", "longshot sell@ask"):
            print(f"  {k}: fill rate {fills[k, 'filled']}/{fills[k, 'tried']}")
            for half in "AB":
                v = out[k, half]
                if len(v) < 10:
                    continue
                lo, hi = boot([x for _, x in v], [e for e, _ in v], n=1000)
                print(f"    {half} n={len(v):4d} pnl/contract {mean([x for _, x in v]):+.4f} [{lo:+.4f},{hi:+.4f}]")


if __name__ == "__main__":
    main()
