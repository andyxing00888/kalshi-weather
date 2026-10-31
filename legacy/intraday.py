"""Intraday test: running observed high + bias-corrected ensemble forecast vs Kalshi price.

At check hour T (local standard time, which is the NWS climate-day clock) on each event day:
  M  = max hourly ASOS temp observed so far that day
  mu = max(M, Hf) + walk-forward bias, Hf = bias-corrected 5-model day-ahead forecast high
  final high ~ Normal(mu, sigma) truncated below at M - 1, sigma from earlier days' residuals.
Compared against the last hourly candle at or before T.
Usage: python3 -m legacy.intraday [T ...]   (default 11 13 15)
Needs data/markets.csv, candles.csv, forecasts_multi.csv, obs.csv.
"""
import collections, math, os, sys
from datetime import datetime, timedelta, timezone
from kalshi.api import edate, fnum
from kalshi.fees import fee
from kalshi.stats import boot, cdf, mean
from legacy.analyze import rd

EDGE = float(os.environ.get("EDGE", 0.05))
STD_OFFSET = {"KXHIGHNY": -5, "KXHIGHCHI": -6, "KXHIGHMIA": -5, "KXHIGHAUS": -6,
              "KXHIGHLAX": -8, "KXHIGHDEN": -7, "KXHIGHPHIL": -5}
MODELS = ["gfs_seamless", "ecmwf_ifs025", "icon_seamless", "gem_seamless", "ukmo_seamless"]


def bucket_p(m, mu, s, floor):
    lo_, hi_ = fnum(m["floor"]), fnum(m["cap"])
    z = cdf(floor, mu, s)

    def F(x):  # P(high <= x), truncated below at floor
        return 0.0 if x <= floor else (cdf(x, mu, s) - z) / max(1 - z, 1e-9)
    st = m["strike_type"]
    if st == "between":
        return F(hi_ + 0.5) - F(lo_ - 0.5)
    if st == "greater":
        return 1 - F(lo_ + 0.5)
    if st == "less":
        return F(hi_ - 0.5)
    return None


def main():
    hours = [int(a) for a in sys.argv[1:]] or [11, 13, 15]
    markets = rd("markets.csv")
    truth = {}
    for m in markets:
        v = fnum(m["value"])
        if v is not None:
            truth[(m["series"], edate(m["event"]))] = v
    multi = {(r["series"], r["date"]): {k[3:]: float(v) for k, v in r.items()
                                        if k.startswith("fc_") and v != ""}
             for r in rd("forecasts_multi.csv")}
    # hourly obs keyed by (series, LST date) -> [(LST hour float, tmpf)]
    obs = collections.defaultdict(list)
    for r in rd("obs.csv"):
        t = datetime.strptime(r["valid_utc"], "%Y-%m-%d %H:%M") + timedelta(hours=STD_OFFSET[r["series"]])
        obs[(r["series"], t.strftime("%Y-%m-%d"))].append((t.hour + t.minute / 60, float(r["tmpf"])))
    candles = collections.defaultdict(list)
    for c in rd("candles.csv"):
        if c["price_close"]:
            candles[c["ticker"]].append(c)
    by_event = collections.defaultdict(list)
    for m in markets:
        by_event[(m["series"], edate(m["event"]))].append(m)

    for T in hours:
        recs = []  # (event, p, q, y, pnl)
        for s_ in STD_OFFSET:
            dates = sorted(d for (ss, d) in multi if ss == s_)
            fc_hist, resid = [], []  # walk-forward stores
            for d in dates:
                cur = multi[(s_, d)]
                prior = [x for x in dates if x < d and (s_, x) in truth][-30:]
                parts = []
                for mdl in MODELS:
                    h = [truth[(s_, x)] - multi[(s_, x)][mdl] for x in prior if mdl in multi[(s_, x)]]
                    if mdl in cur and len(h) >= 10:
                        parts.append(cur[mdl] + mean(h))
                ob = [v for hr, v in obs.get((s_, d), []) if hr <= T]
                if len(parts) < 3 or len(ob) < T - 2:
                    continue
                M = max(ob)
                base = max(M, mean(parts))
                r = resid[-40:]
                if len(r) >= 15 and (s_, d) in by_event:
                    b = mean(r)
                    sg = max(math.sqrt(mean([(e - b) ** 2 for e in r])), 0.5)
                    t_utc = (datetime.strptime(d, "%Y-%m-%d") + timedelta(hours=T - STD_OFFSET[s_])
                             ).replace(tzinfo=timezone.utc).timestamp()
                    for m in by_event[(s_, d)]:
                        cs = [c for c in candles[m["ticker"]] if float(c["end_ts"]) <= t_utc]
                        if not cs:
                            continue
                        c = max(cs, key=lambda c: float(c["end_ts"]))
                        p = bucket_p(m, base + b, sg, M - 1)
                        q, y = float(c["price_close"]), 1.0 if m["result"] == "yes" else 0.0
                        ask, bid = fnum(c["ask_close"]), fnum(c["bid_close"])
                        pnl = None
                        if ask and p - ask > EDGE:
                            pnl = y - ask - fee(ask)
                        elif bid and bid - p > EDGE:
                            pnl = bid - y - fee(1 - bid)
                        recs.append((m["event"], p, q, y, pnl))
                if (s_, d) in truth:
                    resid.append(truth[(s_, d)] - base)
        if not recs:
            print(f"T={T}: no data")
            continue
        keys = [r[0] for r in recs]
        diff = [(r[1] - r[3]) ** 2 - (r[2] - r[3]) ** 2 for r in recs]
        lo, hi = boot(diff, keys)
        bm = mean([(r[1] - r[3]) ** 2 for r in recs])
        bk = mean([(r[2] - r[3]) ** 2 for r in recs])
        print(f"T={T:02d} LST  n={len(recs)} events={len(set(keys))}  Brier model {bm:.4f} "
              f"market {bk:.4f} diff {mean(diff):+.4f} [{lo:+.4f},{hi:+.4f}]")
        print("   blend w:", " ".join(f"{w:.1f}:{mean([((1-w)*r[2]+w*r[1]-r[3])**2 for r in recs]):.4f}"
                                     for w in (0, .1, .2, .3, .5)))
        tr = [(r[0], r[4]) for r in recs if r[4] is not None]
        if tr:
            lo, hi = boot([x for _, x in tr], [k for k, _ in tr])
            print(f"   trades edge>{EDGE}: n={len(tr)} pnl/contract {mean([x for _, x in tr]):+.4f} "
                  f"[{lo:+.4f},{hi:+.4f}]")


if __name__ == "__main__":
    main()
