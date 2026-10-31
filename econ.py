"""Backtests on non-weather daily Kalshi series (gas, TSA, ERCOT, index ranges).

Needs data/econ_markets.csv and data/econ_candles.csv from
  SERIES=KXAAAGASD,KXTSAD,KXTXERCOTPEAKD,KXINX,KXNASDAQ100 OUT=econ python3 pull_markets.py 90
Usage: python3 econ.py [hours_before_close ...]   (default 2 6 12)

1) ladder arb: for one event, P(value > K) must fall as K rises; flag bid(K_hi) > ask(K_lo) + fees.
2) price-bin calibration: buy YES at ask / NO at 1-bid by price bin, after taker fee.
3) persistence model: value_D = value_{D-1} + delta, delta drawn from the last 60 daily changes
   (walk-forward; multiplicative for index series). Trade when model vs quote edge > EDGE.
"""
import collections, math, os, sys
from datetime import datetime
from analyze import rd, fnum, fee
from intraday import mean, boot

EDGE = float(os.environ.get("EDGE", 0.05))
LOG = {"KXINX", "KXNASDAQ100"}  # model changes as log returns


def ts(s):
    return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").timestamp()


def value(m):
    return fnum((m["value"] or "").replace(",", ""))


def yes_if(m, v):
    lo, hi, st = fnum(m["floor"]), fnum(m["cap"]), m["strike_type"]
    return {"greater": lambda: v > lo, "greater_or_equal": lambda: v >= lo,
            "less": lambda: v < hi, "less_or_equal": lambda: v <= hi,
            "between": lambda: lo <= v <= hi}.get(st, lambda: None)()


def quote_at(cs, t):
    """Last candle at or before t with a two-sided quote."""
    ok = [c for c in cs if float(c["end_ts"]) <= t and fnum(c["ask_close"]) and fnum(c["bid_close"]) is not None]
    return max(ok, key=lambda c: float(c["end_ts"])) if ok else None


def report(name, recs):
    if not recs:
        print(f"  {name}: no trades")
        return
    xs = [x for _, x in recs]
    lo, hi = boot(xs, [e for e, _ in recs])
    print(f"  {name}: n={len(xs)} events={len({e for e, _ in recs})} pnl/contract {mean(xs):+.4f} [{lo:+.4f},{hi:+.4f}]")


def main():
    hours = [float(a) for a in sys.argv[1:]] or [2, 6, 12]
    markets = [m for m in rd("econ_markets.csv") if m["result"] in ("yes", "no")]
    candles = collections.defaultdict(list)
    for c in rd("econ_candles.csv"):
        candles[c["ticker"]].append(c)
    events = collections.defaultdict(list)
    for m in markets:
        events[(m["series"], m["event"])].append(m)

    for series in sorted({s for s, _ in events}):
        evs = sorted(((e, ms) for (s, e), ms in events.items() if s == series), key=lambda x: ts(x[1][0]["close_time"]))
        vals = [value(ms[0]) for _, ms in evs]
        print(f"\n=== {series}: {len(evs)} events, {sum(len(ms) for _, ms in evs)} markets")

        # 1) ladder arb over every candle hour
        arb, checked = [], 0
        for e, ms in evs:
            lad = sorted((m for m in ms if m["strike_type"] in ("greater", "greater_or_equal")), key=lambda m: fnum(m["floor"]))
            byt = [{c["end_ts"]: c for c in candles[m["ticker"]]} for m in lad]
            for t in set().union(*byt) if byt else ():
                for i in range(len(lad) - 1):
                    a, b = byt[i].get(t), byt[i + 1].get(t)
                    if not a or not b:
                        continue
                    ask_lo, bid_hi = fnum(a["ask_close"]), fnum(b["bid_close"])
                    if not ask_lo or not bid_hi:
                        continue
                    checked += 1
                    edge = bid_hi - ask_lo - fee(ask_lo) - fee(1 - bid_hi)
                    if edge > 0:
                        arb.append((e, edge))
        print(f"  ladder arb: {checked} adjacent-strike quotes checked, {len(arb)} profitable after fees"
              + (f" in {len({e for e, _ in arb})} events, median {sorted(x for _, x in arb)[len(arb) // 2]:.3f}" if arb else ""))

        for H in hours:
            bins = collections.defaultdict(list)
            model = []
            for k, (e, ms) in enumerate(evs):
                t = ts(ms[0]["close_time"]) - H * 3600
                prev = vals[k - 1] if k else None
                hist = [(vals[j] / vals[j - 1] if series in LOG else vals[j] - vals[j - 1])
                        for j in range(max(1, k - 60), k) if vals[j] is not None and vals[j - 1]]
                for m in ms:
                    q = quote_at(candles[m["ticker"]], t)
                    if not q:
                        continue
                    a, b = fnum(q["ask_close"]), fnum(q["bid_close"])
                    y = 1.0 if m["result"] == "yes" else 0.0
                    if 0 < a < 1:
                        bins["yes", min(int(a * 10), 9)].append((e, y - a - fee(a)))
                    if 0 < b < 1:
                        bins["no", min(int((1 - b) * 10), 9)].append((e, b - y - fee(1 - b)))
                    if prev is not None and len(hist) >= 15:
                        outs = [yes_if(m, prev * d if series in LOG else prev + d) for d in hist]
                        if None in outs:
                            continue
                        p = (sum(outs) + 0.5) / (len(outs) + 1)
                        if 0 < a < 1 and p - a > EDGE:
                            model.append((e, y - a - fee(a)))
                        elif 0 < b < 1 and b - p > EDGE:
                            model.append((e, b - y - fee(1 - b)))
            print(f" -- {H:g}h before close")
            for side in ("yes", "no"):
                row = []
                for i in range(10):
                    r = bins[side, i]
                    if len(r) >= 30:
                        row.append(f"{i / 10:.1f}:{mean([x for _, x in r]) * 100:+.1f}¢({len(r)})")
                print(f"  buy {side.upper():3s} by cost bin: " + " ".join(row))
            report(f"persistence model edge>{EDGE}", model)


if __name__ == "__main__":
    main()
