"""Backtest every rule in strategies.py on settled markets, maker fills with trade-through.

Usage: python3 -m paper.explore [H ...]   (hours before close, default 36 30 24 18)
Reports per rule x horizon, by first/second half of event dates, event-clustered 95% CIs.
"""
import collections, json, os, sys

from kalshi.api import edate, fnum as f, iso_ts
from kalshi.fills import fill_pnl
from kalshi.paths import DATA
from kalshi.stats import boot, mean
from kalshi.store import read
from paper.strategies import RULES


def quote(cs, t):
    prev = [c for c in cs if c["end_period_ts"] <= t]
    if not prev:
        return None
    c = prev[-1]
    b, a = f(c["yes_bid"]["close_dollars"]), f(c["yes_ask"]["close_dollars"])
    return (b, a) if b is not None and a is not None and 0 <= b < a <= 1 else None


def main():
    hs = [int(a) for a in sys.argv[1:]] or [36, 30, 24, 18]
    markets = read(os.path.join(DATA, "markets.csv"))
    ev = collections.defaultdict(list)
    for m in markets:
        m["cs"] = json.load(open(os.path.join(DATA, "cache", m["ticker"] + ".json")))
        m["close"] = iso_ts(m["close_time"])
        ev[m["event"]].append(m)
    dates = sorted({edate(e) for e in ev})
    split = dates[len(dates) // 2]
    key = lambda m: float(m["floor"] or -999) if m["strike_type"] != "less" else -1000.0
    print(f"{len(ev)} events, train/test split at {split}; P&L per contract after maker fee\n")
    print(f"{'rule':13s} {'H':>3s}  {'half A n':>8s} {'pnl':>7s} {'95% CI':>17s}   {'half B n':>8s} {'pnl':>7s} {'95% CI':>17s}")
    for name, rule in RULES.items():
        for H in hs:
            res = collections.defaultdict(list)
            for e, ms in ev.items():
                t0 = ms[0]["close"] - H * 3600
                snap = []
                for m in sorted(ms, key=key):
                    q, q0 = quote(m["cs"], t0), quote(m["cs"], t0 - 6 * 3600)
                    if q is None:
                        snap = None
                        break
                    snap.append(dict(ticker=m["ticker"], strike_type=m["strike_type"], floor=m["floor"],
                                     cap=m["cap"], bid=q[0], ask=q[1], mid=(q[0] + q[1]) / 2,
                                     prev_mid=(q0[0] + q0[1]) / 2 if q0 else None, m=m))
                if not snap:
                    continue
                for t, side in rule(snap).items():
                    s = next(x for x in snap if x["ticker"] == t)
                    if s["bid"] <= 0 or s["ask"] >= 1:
                        continue
                    px = s["bid"] if side == "buy_yes" else s["ask"]
                    p = fill_pnl(side, px, 1.0 if s["m"]["result"] == "yes" else 0.0, s["m"]["cs"], t0)
                    if p is not None:
                        res["A" if edate(e) < split else "B"].append((e, p))
            cells = []
            for half in "AB":
                v = res[half]
                if len(v) < 15:
                    cells.append(f"{len(v):8d} {'':>7s} {'':>17s}")
                    continue
                lo, hi = boot([x for _, x in v], [k for k, _ in v])
                cells.append(f"{len(v):8d} {mean([x for _, x in v]):+7.4f} [{lo:+.4f},{hi:+.4f}]")
            print(f"{name:13s} {H:3d}  {cells[0]}   {cells[1]}")


if __name__ == "__main__":
    main()
