"""Where on Kalshi is the favorite-longshot bias big enough to trade? Calibration across categories.

Samples recently settled markets from the highest-volume series (parlays and markets open < 3h
excluded; hourly candles can't resolve them), reads the quote at 24h, 3h and half-life before close,
and scores, per category / series / price bin:
  taker  buy YES at ask, sell YES at bid (taker fee)
  maker  sell_longshot: offer YES at the ask when mid in [0.03, 0.15)
         buy_favorite:  bid YES at the bid when mid in [0.85, 0.97)   (the "high-probability bond")
         filled only on a trade through the price within 6h (kalshi.fills.fill_pnl), maker fee
Usage: python3 calib.py pull [days] [series] [per_series]   (defaults 21, 150, 40)
       EXCLUDE=Sports python3 calib.py pull ...              skip categories (comma list)
       python3 calib.py                                      report
"""
import collections, csv, json, os, random, sys, time
from kalshi.api import get, fnum, iso_ts
from kalshi.fees import fee
from kalshi.fills import fill_pnl
from kalshi.stats import boot, mean
from kalshi.paths import DATA

CACHE = os.path.join(DATA, "cache_calib")
ROWS = os.path.join(DATA, os.environ.get("ROWS", "calib.csv"))
HOURS = ("24", "3", "half")
MIN_LIFE_H = 3
MAX_SPREAD = 0.05


def universe(days, max_pages=150):
    now, cur, out = int(time.time()), None, []
    for _ in range(max_pages):
        p = dict(status="settled", limit=1000, min_close_ts=now - days * 86400, mve_filter="exclude")
        if cur:
            p["cursor"] = cur
        d = get("/markets", **p)
        out += [m for m in d["markets"] if m.get("result") in ("yes", "no")
                and (iso_ts(m["close_time"]) - iso_ts(m["open_time"])) / 3600 >= MIN_LIFE_H]
        cur = d.get("cursor")
        if not cur:
            break
    return out


def pull(days, n_series, per_series):
    cats = {s["ticker"]: s.get("category") or "?" for s in get("/series")["series"]}
    ms = universe(days)
    by = collections.defaultdict(list)
    for m in ms:
        by[m["event_ticker"].split("-")[0]].append(m)
    vol = {s: sum(fnum(m.get("volume_fp")) or 0 for m in v) for s, v in by.items()}
    skip = set(filter(None, os.environ.get("EXCLUDE", "").split(",")))
    top = [s for s in sorted(vol, key=lambda s: -vol[s]) if cats.get(s, "?") not in skip][:n_series]
    print(f"{len(ms)} settled markets in {len(by)} series; sampling {per_series} from top {len(top)}", flush=True)
    rng, rows = random.Random(0), []
    os.makedirs(CACHE, exist_ok=True)
    for i, s in enumerate(top):
        pool = [m for m in by[s] if (fnum(m.get("volume_fp")) or 0) >= 10]
        for m in rng.sample(pool, min(per_series, len(pool))):
            t0, t1 = int(iso_ts(m["open_time"])), int(iso_ts(m["close_time"]))
            cp = os.path.join(CACHE, m["ticker"] + ".json")
            if os.path.exists(cp):
                cs = json.load(open(cp))
            else:
                cs = get(f"/series/{s}/markets/{m['ticker']}/candlesticks",
                         start_ts=max(t0, t1 - 26 * 3600), end_ts=t1, period_interval=60)["candlesticks"]
                json.dump(cs, open(cp, "w"))
                time.sleep(0.03)
            rows.append(dict(series=s, category=cats.get(s, "?"), event=m["event_ticker"], ticker=m["ticker"],
                             open=t0, close=t1, result=m["result"]))
        if i % 25 == 24:
            print(f"  {i + 1} series", flush=True)
    with open(ROWS, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("wrote", len(rows))


def quote(cs, t):
    ok = [c for c in cs if c["end_period_ts"] <= t and fnum(c["yes_bid"].get("close_dollars")) is not None
          and fnum(c["yes_ask"].get("close_dollars")) is not None]
    if not ok:
        return None
    c = max(ok, key=lambda c: c["end_period_ts"])
    if t - c["end_period_ts"] > 2 * 3600:
        return None
    return fnum(c["yes_bid"]["close_dollars"]), fnum(c["yes_ask"]["close_dollars"])


def report():
    rows = list(csv.DictReader(open(ROWS)))
    R = collections.defaultdict(list)  # (scope, key, rule, H) -> [(event, pnl)]
    for r in rows:
        cs = json.load(open(os.path.join(CACHE, r["ticker"] + ".json")))
        t0, t1, y = int(r["open"]), int(r["close"]), 1.0 if r["result"] == "yes" else 0.0
        for H in HOURS:
            t = t1 - 3600 * int(H) if H != "half" else (t0 + t1) // 2
            t = t - t % 3600  # candles end on the hour
            if t <= t0:
                continue
            q = quote(cs, t)
            if not q:
                continue
            b, a = q
            if not (0 < b < a < 1) or a - b > MAX_SPREAD:  # wide books are not prices
                continue
            mid = (a + b) / 2
            out = {f"buyYES_{int(a * 10)}": y - a - fee(a), f"sellYES_{int(b * 10)}": b - y - fee(1 - b)}
            if .03 <= mid < .15:
                p = fill_pnl("sell_yes", a, y, cs, t)
                if p is not None:
                    out["mk_sell_longshot"] = p
            if .85 <= mid < .97:
                p = fill_pnl("buy_yes", b, y, cs, t)
                if p is not None:
                    out["mk_buy_favorite"] = p
            for rule, p in out.items():
                for scope, key in (("all", "all"), ("cat", r["category"]), ("series", r["series"])):
                    R[scope, key, rule, H].append((r["event"], p))

    def line(xs):
        pn = [x for _, x in xs]
        lo, hi = boot(pn, [e for e, _ in xs], n=400)
        return f"n={len(pn):5d} ev={len({e for e, _ in xs}):4d} {mean(pn) * 100:+5.1f}¢ [{lo * 100:+5.1f},{hi * 100:+5.1f}]"

    print(f"{len(rows)} markets, {len({r['series'] for r in rows})} series, {len({r['event'] for r in rows})} events")
    for H in HOURS:
        print(f"\n=== all series, {H}{'h' if H != 'half' else '-life'} before close")
        for rule in ["mk_sell_longshot", "mk_buy_favorite"] + [f"buyYES_{i}" for i in range(10)] + [f"sellYES_{i}" for i in range(10)]:
            xs = R.get(("all", "all", rule, H))
            if xs and len(xs) >= 30:
                print(f"  {rule:17s} {line(xs)}")
    for rule in ("mk_sell_longshot", "mk_buy_favorite", "buyYES_0", "sellYES_9"):
        print(f"\n=== {rule} by category (all horizons pooled)")
        pooled = collections.defaultdict(list)
        for (scope, key, rr, H), xs in R.items():
            if scope == "cat" and rr == rule:
                pooled[key] += xs
        for key, xs in sorted(pooled.items(), key=lambda kv: -mean([x for _, x in kv[1]])):
            if len(xs) >= 30:
                print(f"  {key[:24]:24s} {line(xs)}")
    print("\n=== series where mk_sell_longshot / mk_buy_favorite look best (n>=40, pooled horizons)")
    for rule in ("mk_sell_longshot", "mk_buy_favorite"):
        pooled = collections.defaultdict(list)
        for (scope, key, rr, H), xs in R.items():
            if scope == "series" and rr == rule:
                pooled[key] += xs
        best = sorted((kv for kv in pooled.items() if len(kv[1]) >= 40), key=lambda kv: -mean([x for _, x in kv[1]]))
        for key, xs in best[:12]:
            print(f"  {rule} {key[:26]:26s} {line(xs)}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "pull":
        a = [int(x) for x in sys.argv[2:]]
        pull(*(a + [21, 150, 40][len(a):]))
    else:
        report()
