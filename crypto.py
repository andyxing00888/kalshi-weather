"""Crypto daily ("BTC above K at 5pm ET") vs a spot model: does Kalshi lag the underlying?

KXBTCD / KXETHD 5pm events settle on the 60s average of CF Benchmarks' index; Coinbase spot is a
close proxy. Fair value at t: P(S_T > K) = N(ln(S_t/K) / (sigma sqrt(T-t))), no drift, sigma from the
last 7 days of hourly log returns (walk-forward, no look-ahead). Strikes are chosen within +-STRIKE_BAND
of spot 24h before close, so selection doesn't peek at the outcome.
Reports, per hours-before-close: Brier of the Kalshi mid vs the model, taker P&L when the model beats
the quote by EDGE after fees, and the same with the model's edge ignored (all quotes) as a control.
Usage: python3 crypto.py pull [days]   cache Kalshi markets/candles + Coinbase hourly
       python3 crypto.py [EDGE ...]    report (default 0.03 0.06 0.10)
"""
import collections, json, math, os, sys, time, urllib.request
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper"))
from common import get, fnum, boot, mean, iso_ts, fee  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CACHE = os.path.join(DATA, "cache_crypto")
COINS = {"KXBTCD": "BTC-USD", "KXETHD": "ETH-USD"}
STRIKE_BAND, HOURS, MAX_SPREAD = 0.04, (1, 3, 6, 12, 20), 0.05


def spot_history(product, days):
    """{hour_ts: close} from Coinbase, 300 candles per request."""
    path = os.path.join(CACHE, f"{product}.json")
    out = {int(k): v for k, v in json.load(open(path)).items()} if os.path.exists(path) else {}
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days + 8)
    t = start
    while t < end:
        t2 = min(t + timedelta(hours=300), end)
        url = (f"https://api.exchange.coinbase.com/products/{product}/candles?granularity=3600"
               f"&start={t:%Y-%m-%dT%H:%M:%SZ}&end={t2:%Y-%m-%dT%H:%M:%SZ}")
        req = urllib.request.Request(url, headers={"User-Agent": "kalshi-research"})
        for c in json.load(urllib.request.urlopen(req, timeout=30)):
            out[int(c[0]) + 3600] = c[4]  # candle [start, low, high, open, close]: close at start + 1h
        t = t2
        time.sleep(0.3)
    json.dump(out, open(path, "w"))
    return out


def pull(days):
    os.makedirs(CACHE, exist_ok=True)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    for series, product in COINS.items():
        spot = spot_history(product, days)
        mpath = os.path.join(CACHE, f"{series}_markets.json")
        evs = json.load(open(mpath)) if os.path.exists(mpath) else {}
        cur = None
        while True:
            p = dict(series_ticker=series, status="settled", limit=200)
            if cur:
                p["cursor"] = cur
            d = get("/events", **p)
            for e in d["events"]:
                et = e["event_ticker"]
                if not et.endswith("17") or et in evs:
                    continue
                ms = get("/markets", event_ticker=et, limit=500)["markets"]
                if not ms or iso_ts(ms[0]["close_time"]) < since.timestamp():
                    continue
                close = iso_ts(ms[0]["close_time"])
                s0 = spot.get(int(close - 24 * 3600))
                if not s0:
                    continue
                keep = [m for m in ms if m["strike_type"] == "greater" and m.get("result") in ("yes", "no")
                        and abs(m["floor_strike"] / s0 - 1) <= STRIKE_BAND]
                for m in keep:
                    cp = os.path.join(CACHE, m["ticker"] + ".json")
                    if not os.path.exists(cp):
                        cs = get(f"/series/{series}/markets/{m['ticker']}/candlesticks",
                                 start_ts=int(max(iso_ts(m["open_time"]), close - 26 * 3600)), end_ts=int(close),
                                 period_interval=60)["candlesticks"]
                        json.dump(cs, open(cp, "w"))
                        time.sleep(0.03)
                evs[et] = [dict(ticker=m["ticker"], strike=m["floor_strike"], result=m["result"],
                                close=close, value=m.get("expiration_value")) for m in keep]
                json.dump(evs, open(mpath, "w"))
                print(series, et, len(keep), "strikes", flush=True)
            cur = d.get("cursor")
            oldest = d["events"][-1]["event_ticker"] if d["events"] else None
            if not cur or (oldest and datetime.strptime(oldest.split("-")[1][:7], "%y%b%d").replace(
                    tzinfo=timezone.utc) < since):
                break


def ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def report(edges):
    for series, product in COINS.items():
        spot = {int(k): v for k, v in json.load(open(os.path.join(CACHE, f"{product}.json"))).items()}
        evs = json.load(open(os.path.join(CACHE, f"{series}_markets.json")))
        R = collections.defaultdict(list)
        brier = collections.defaultdict(lambda: [0.0, 0.0, 0])
        for et, ms in evs.items():
            for m in ms:
                cs = {c["end_period_ts"]: c for c in json.load(open(os.path.join(CACHE, m["ticker"] + ".json")))}
                y = 1.0 if m["result"] == "yes" else 0.0
                for H in HOURS:
                    t = int(m["close"] - H * 3600)
                    c, s = cs.get(t), spot.get(t)
                    rets = [math.log(spot[t - 3600 * (i + 1) + 3600] / spot[t - 3600 * (i + 1)])
                            for i in range(168) if spot.get(t - 3600 * (i + 1)) and spot.get(t - 3600 * i)]
                    if not c or not s or len(rets) < 100:
                        continue
                    b, a = fnum(c["yes_bid"].get("close_dollars")), fnum(c["yes_ask"].get("close_dollars"))
                    if b is None or a is None or not (0 < b < a < 1) or a - b > MAX_SPREAD:
                        continue
                    sig = math.sqrt(sum(r * r for r in rets) / len(rets))  # per hour
                    p = ncdf(math.log(s / m["strike"]) / (sig * math.sqrt(H)))
                    mid = (a + b) / 2
                    br = brier[H]
                    br[0] += (mid - y) ** 2
                    br[1] += (p - y) ** 2
                    br[2] += 1
                    R["all quotes", H].append((et, y - a - fee(a)))
                    for E in edges:
                        if p - a - fee(a) > E:
                            R[f"model edge>{E:.2f}", H].append((et, y - a - fee(a)))
                        elif b - p - fee(1 - b) > E:
                            R[f"model edge>{E:.2f}", H].append((et, b - y - fee(1 - b)))
        print(f"\n=== {series}: {len(evs)} days")
        for H in HOURS:
            km, mm, n = brier[H]
            if n:
                print(f"  {H:2d}h  n={n:4d}  Brier kalshi {km / n:.4f}  model {mm / n:.4f}")
        for (name, H), xs in sorted(R.items()):
            if len(xs) >= 10:
                pn = [x for _, x in xs]
                lo, hi = boot(pn, [e for e, _ in xs], n=500)
                print(f"  {name:16s} {H:2d}h n={len(pn):4d} days={len({e for e, _ in xs}):3d} "
                      f"{mean(pn) * 100:+5.1f}¢ [{lo * 100:+5.1f},{hi * 100:+5.1f}]")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "pull":
        pull(int(sys.argv[2]) if len(sys.argv) > 2 else 60)
    else:
        report([float(x) for x in sys.argv[1:]] or [0.03, 0.06, 0.10])
