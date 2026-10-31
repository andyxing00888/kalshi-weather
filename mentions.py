"""Mentions markets ("Will Trump say X?"): retail-heavy, and the same words recur across events.

  pull     settled markets from the top mention series (by volume) + hourly candles, written in
           calib.py's format to data/calib_mentions.csv, so `ROWS=calib_mentions.csv python3 calib.py`
           gives the calibration / longshot tables for mentions alone
  (report) word base rates, walk-forward: for each market, the YES rate of the same word (yes_sub_title)
           in earlier events of the same series (Laplace prior, >= MIN_PRIOR earlier events);
           taker trade at H hours before close when base rate beats the quote by EDGE after fees
Usage: python3 mentions.py pull [n_series] [per_series]   (defaults 40, 150)
       python3 mentions.py [EDGE ...]                     (default 0.05 0.10 0.20)
"""
import collections, csv, json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper"))
from common import get, fnum, boot, mean, iso_ts, fee  # noqa: E402
import calib  # noqa: E402

ROWS = os.path.join(calib.DATA, "calib_mentions.csv")
HOURS, MIN_PRIOR = (24, 6, 2), 3


def settled(series, cap=3000):
    out, cur = [], None
    while len(out) < cap:
        p = dict(series_ticker=series, status="settled", limit=1000)
        if cur:
            p["cursor"] = cur
        d = get("/markets", **p)
        out += [m for m in d["markets"] if m.get("result") in ("yes", "no")]
        cur = d.get("cursor")
        if not cur:
            break
    return out


def pull(n_series, per_series):
    ss = [s["ticker"] for s in get("/series")["series"] if "SAY" in s["ticker"] or "MENTION" in s["ticker"]]
    vol = {}
    for s in ss:
        try:
            ms = get("/markets", series_ticker=s, status="settled", limit=200)["markets"]
        except RuntimeError:
            continue
        vol[s] = sum(fnum(m.get("volume_fp")) or 0 for m in ms)
    top = sorted(vol, key=lambda s: -vol[s])[:n_series]
    rows = []
    os.makedirs(calib.CACHE, exist_ok=True)
    for i, s in enumerate(top):
        ms = sorted(settled(s), key=lambda m: m["close_time"])[-per_series:]
        for m in ms:
            if (fnum(m.get("volume_fp")) or 0) < 10:
                continue
            t0, t1 = int(iso_ts(m["open_time"])), int(iso_ts(m["close_time"]))
            cp = os.path.join(calib.CACHE, m["ticker"] + ".json")
            if not os.path.exists(cp):
                cs = get(f"/series/{s}/markets/{m['ticker']}/candlesticks",
                         start_ts=max(t0, t1 - 26 * 3600), end_ts=t1, period_interval=60)["candlesticks"]
                json.dump(cs, open(cp, "w"))
                time.sleep(0.03)
            rows.append(dict(series=s, category="Mentions", event=m["event_ticker"], ticker=m["ticker"],
                             open=t0, close=t1, result=m["result"],
                             word=(m.get("yes_sub_title") or m["ticker"].rsplit("-", 1)[1]).strip().lower()))
        print(f"  {i + 1}/{len(top)} {s}: {len(ms)} markets", flush=True)
    with open(ROWS, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("wrote", len(rows))


def report(edges):
    rows = sorted(csv.DictReader(open(ROWS)), key=lambda r: int(r["close"]))
    hist = collections.defaultdict(list)  # (series, word) -> [(close, y)]
    R, cover = collections.defaultdict(list), collections.Counter()
    for r in rows:
        y = 1.0 if r["result"] == "yes" else 0.0
        key, close = (r["series"], r["word"]), int(r["close"])
        past = [v for c, v in hist[key] if c < close - 86400]  # earlier events only
        hist[key].append((close, y))
        cover["markets"] += 1
        if len(past) < MIN_PRIOR:
            continue
        cover["with base rate"] += 1
        base = (sum(past) + 1) / (len(past) + 2)
        cs = json.load(open(os.path.join(calib.CACHE, r["ticker"] + ".json")))
        for H in HOURS:
            t = close - H * 3600
            q = calib.quote(cs, t - t % 3600)
            if not q or not (0 < q[0] < q[1] < 1) or q[1] - q[0] > 0.10:
                continue
            b, a = q
            R["all quotes buy YES", H].append((r["event"], y - a - fee(a)))
            R["all quotes sell YES", H].append((r["event"], b - y - fee(1 - b)))
            for E in edges:
                if base - a - fee(a) > E:
                    R[f"base edge>{E:.2f}", H].append((r["event"], y - a - fee(a)))
                elif b - base - fee(1 - b) > E:
                    R[f"base edge>{E:.2f}", H].append((r["event"], b - y - fee(1 - b)))
    print(f"{cover['markets']} mention markets, {cover['with base rate']} with >= {MIN_PRIOR} earlier events of the same word")
    for (name, H), xs in sorted(R.items()):
        if len(xs) >= 10:
            pn = [x for _, x in xs]
            lo, hi = boot(pn, [e for e, _ in xs], n=500)
            print(f"  {name:20s} {H:2d}h n={len(pn):5d} ev={len({e for e, _ in xs}):4d} "
                  f"{mean(pn) * 100:+5.1f}¢ [{lo * 100:+5.1f},{hi * 100:+5.1f}]")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "pull":
        a = [int(x) for x in sys.argv[2:]]
        pull(*(a + [40, 150][len(a):]))
    else:
        report([float(x) for x in sys.argv[1:]] or [0.05, 0.10, 0.20])
