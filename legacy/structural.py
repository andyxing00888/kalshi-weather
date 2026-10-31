"""Structural (forecast-free) edges on settled Kalshi temperature markets.

1. Calibration by price bin and horizon: realized YES rate vs quoted price (favorite-longshot bias).
2. Rule search on the first half of event dates, out-of-sample test on the second half:
   buy YES at ask or buy NO at (1 - bid) when the quote falls in a price bin, after fees.
3. Dutch book: per event and hour, sum of YES asks < 1 (buy every bucket) or sum of bids > 1.
Usage: python3 -m legacy.structural
"""
import collections
from kalshi.api import edate, fnum, iso_ts
from kalshi.fees import fee
from kalshi.stats import boot, mean
from legacy.analyze import rd


HORIZONS = [40, 30, 24, 18, 12]  # hours before close_time
BINS = [0, .03, .06, .10, .15, .25, .40, .60, .75, .85, .90, .94, .97, 1.0]


def binof(x):
    for a, b in zip(BINS, BINS[1:]):
        if a <= x < b:
            return (a, b)
    return (BINS[-2], 1.0)


def main():
    markets = rd("markets.csv")
    candles = collections.defaultdict(dict)
    for c in rd("candles.csv"):
        candles[c["ticker"]][int(float(c["end_ts"]))] = c
    dates = sorted({edate(m["event"]) for m in markets})
    split = dates[len(dates) // 2]
    print(f"{len(dates)} event dates; train < {split} <= test")

    # quote at each horizon: (h, event, date, y, bid, ask)
    rows = []
    for m in markets:
        close = int(iso_ts(m["close_time"]))
        cs = candles[m["ticker"]]
        ts = sorted(cs)
        y = 1.0 if m["result"] == "yes" else 0.0
        for h in HORIZONS:
            cut = close - h * 3600
            prev = [t for t in ts if t <= cut]
            if not prev:
                continue
            c = cs[prev[-1]]
            bid, ask = fnum(c["bid_close"]), fnum(c["ask_close"])
            if bid is None or ask is None or not (0 < bid < ask < 1):
                continue
            rows.append((h, m["event"], edate(m["event"]), y, bid, ask, m["ticker"]))

    print("\n1) calibration: realized YES rate by mid-price bin (all horizons pooled, events counted once per bin)")
    cal = collections.defaultdict(list)
    for h, ev, d, y, bid, ask, _ in rows:
        cal[binof((bid + ask) / 2)].append((y, (bid + ask) / 2, ev))
    print("  bin          n    mid   yes_rate  yes-mid")
    for b in sorted(cal):
        v = cal[b]
        print(f"  {b[0]:.2f}-{b[1]:.2f} {len(v):6d} {mean([x[1] for x in v]):.3f}  "
              f"{mean([x[0] for x in v]):.3f}   {mean([x[0] - x[1] for x in v]):+.3f}")

    print("\n2) rules: side x horizon x price bin; pick on train, evaluate on test (after fee, at quote)")

    def pnl(side, y, bid, ask):
        return y - ask - fee(ask) if side == "yes" else bid - y - fee(1 - bid)

    perf = collections.defaultdict(lambda: {"train": [], "test": []})
    for h, ev, d, y, bid, ask, _ in rows:
        for side in ("yes", "no"):
            px = ask if side == "yes" else bid
            perf[(side, h, binof(px))]["train" if d < split else "test"].append((ev, pnl(side, y, bid, ask)))
    picked = [(k, v) for k, v in perf.items()
              if len(v["train"]) >= 60 and mean([x for _, x in v["train"]]) > 0]
    picked.sort(key=lambda kv: -mean([x for _, x in kv[1]["train"]]))
    print("  side h   price bin    train_n train_pnl  test_n test_pnl  test 95% CI")
    allt = []
    for (side, h, b), v in picked:
        tr, te = v["train"], v["test"]
        if len(te) < 20:
            continue
        lo, hi = boot([x for _, x in te], [e for e, _ in te], n=1000)
        allt += te
        print(f"  {side:3s} {h:3d} {b[0]:.2f}-{b[1]:.2f}  {len(tr):6d} {mean([x for _, x in tr]):+.4f}  "
              f"{len(te):6d} {mean([x for _, x in te]):+.4f}  [{lo:+.4f},{hi:+.4f}]")
    if allt:
        lo, hi = boot([x for _, x in allt], [e for e, _ in allt], n=1000)
        print(f"  ALL picked rules on test: n={len(allt)} pnl {mean([x for _, x in allt]):+.4f} [{lo:+.4f},{hi:+.4f}]")

    print("\n3) dutch book: per event-hour, sum of asks and sum of bids across all buckets")
    ev_tickers = collections.defaultdict(set)
    for m in markets:
        ev_tickers[m["event"]].add(m["ticker"])
    hits_buy, hits_sell, n = [], [], 0
    for ev, tks in ev_tickers.items():
        common = set.intersection(*(set(candles[t]) for t in tks)) if tks else set()
        for t in common:
            qs = [candles[k][t] for k in tks]
            a = [fnum(q["ask_close"]) for q in qs]
            b = [fnum(q["bid_close"]) for q in qs]
            if None in a or None in b:
                continue
            n += 1
            cost = sum(a) + sum(fee(x) for x in a)
            if cost < 1:
                hits_buy.append((ev, t, 1 - cost))
            proceeds = sum(b) - sum(fee(1 - x) for x in b)
            if proceeds > len(tks) - 1 + 1e-9:  # buy NO on all: pays len-1, costs sum(1-b)
                hits_sell.append((ev, t, proceeds - (len(tks) - 1)))
    print(f"  event-hours checked {n}; buy-all-yes profitable {len(hits_buy)}; buy-all-no profitable {len(hits_sell)}")
    for name, hs in (("buy-all-yes", hits_buy), ("buy-all-no", hits_sell)):
        if hs:
            print(f"  {name}: events {len({e for e, _, _ in hs})}, median edge {sorted(x for *_, x in hs)[len(hs)//2]:.3f}, "
                  f"max {max(x for *_, x in hs):.3f}")


if __name__ == "__main__":
    main()
