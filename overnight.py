"""Stale overnight / weekend quotes? KXINXU (S&P >= K at 4pm) vs a fair value from S&P futures.

The futures (ES=F) trade overnight and from Sunday evening; Kalshi's next-day ladder may lag them.
Fair value at hour t for the event closing at T:
  S_hat = ES(t) x prev_close / ES(prev close time)    prev_close = the KXINXDUD strike (yesterday's close)
  P(X >= K) = N(ln(S_hat/K) / (sigma sqrt(tau)))     sigma = 20-day realized daily vol of ^GSPC,
                                                      tau = session fraction left (1 before the open)
Splits overnight/weekend hours (before the 9:30 open) from regular-session hours.
Needs data/cons_markets.json and its candle cache from `python3 consistency.py pull`.
Usage: python3 overnight.py [EDGE ...]   (default 0.03 0.06 0.10)
"""
import collections, json, math, os, sys, urllib.request
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper"))
from common import fnum, boot, mean, iso_ts, fee  # noqa: E402
import consistency as C  # noqa: E402

SESSION_H, MAX_SPREAD = 6.5, 0.05


def yahoo(sym, interval, rng):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval={interval}&range={rng}"
    r = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}),
                                         timeout=30))["chart"]["result"][0]
    step = 3600 if interval == "60m" else 0
    return sorted((t + step, c) for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if c)


def at(series, t):
    """Last value with timestamp <= t."""
    best = None
    for ts, v in series:
        if ts > t:
            break
        best = v
    return best


def ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def main():
    edges = [float(x) for x in sys.argv[1:]] or [0.03, 0.06, 0.10]
    es = yahoo("ES%3DF", "60m", "60d")
    spx = yahoo("%5EGSPC", "1d", "6mo")
    data = {k: v for k, v in json.load(open(C.MKTS)).items() if k.startswith("SPX")}
    closes = sorted(iso_ts(v["range"][0]["close_time"]) for v in data.values())
    R, brier = collections.defaultdict(list), collections.defaultdict(lambda: [0.0, 0.0, 0])
    for key, legs in data.items():
        T = iso_ts(legs["range"][0]["close_time"])
        prev_T = max((c for c in closes if c < T), default=None)
        if not legs.get("updown") or prev_T is None or T - prev_T > 4 * 86400:
            continue
        prev_close = legs["updown"][0]["floor_strike"]
        es_prev = at(es, prev_T)
        rets = [math.log(b / a) for (_, a), (_, b) in zip(spx, spx[1:]) if _ < T - 86400][-20:]
        if not es_prev or len(rets) < 15:
            continue
        sig = math.sqrt(sum(r * r for r in rets) / len(rets))
        for m in legs["above"]:
            K, y = round(m["floor_strike"]), 1.0 if m["result"] == "yes" else 0.0
            for c in json.load(open(os.path.join(C.CACHE, m["ticker"] + ".json"))):
                t = c["end_period_ts"]
                if not prev_T < t < T:
                    continue
                b, a = fnum(c["yes_bid"].get("close_dollars")), fnum(c["yes_ask"].get("close_dollars"))
                e = at(es, t)
                if b is None or a is None or not (0 < b < a < 1) or a - b > MAX_SPREAD or not e:
                    continue
                tau = min(1.0, (T - t) / 3600 / SESSION_H)
                p = ncdf(math.log(e * prev_close / es_prev / K) / (sig * math.sqrt(tau)))
                seg = "overnight" if T - t > SESSION_H * 3600 else "session"
                if seg == "overnight" and t - prev_T > 2 * 86400:
                    seg = "weekend"
                mid = (a + b) / 2
                br = brier[seg]
                br[0] += (mid - y) ** 2
                br[1] += (p - y) ** 2
                br[2] += 1
                for E in edges:
                    if p - a - fee(a) > E:
                        R[seg, E].append((key, y - a - fee(a)))
                    elif b - p - fee(1 - b) > E:
                        R[seg, E].append((key, b - y - fee(1 - b)))
    print(f"{len(data)} S&P event-days; ES hourly {len(es)} bars")
    for seg, (km, mm, n) in sorted(brier.items()):
        print(f"  {seg:9s} n={n:6d}  Brier kalshi {km / n:.4f}  futures model {mm / n:.4f}")
    for (seg, E), xs in sorted(R.items()):
        if len(xs) >= 10:
            pn = [x for _, x in xs]
            lo, hi = boot(pn, [k for k, _ in xs], n=500)
            print(f"  {seg:9s} edge>{E:.2f} n={len(pn):5d} days={len({k for k, _ in xs}):3d} "
                  f"{mean(pn) * 100:+5.1f}¢ [{lo * 100:+5.1f},{hi * 100:+5.1f}]")


if __name__ == "__main__":
    main()
