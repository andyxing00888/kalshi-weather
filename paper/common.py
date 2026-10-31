"""Shared helpers for the paper trader: Kalshi API, maker fee, trade-through fill rule, stats."""
import collections, json, math, random, time, urllib.parse, urllib.request

BASE = "https://api.elections.kalshi.com/trade-api/v2"
SERIES = ["KXHIGHNY", "KXHIGHCHI", "KXHIGHMIA", "KXHIGHAUS", "KXHIGHLAX", "KXHIGHDEN", "KXHIGHPHIL"]
ECON_SERIES = ["KXAAAGASD", "KXTXERCOTPEAKD", "KXINX", "KXNASDAQ100"]  # daily, open only 16-24h
# calib.py: buying YES under 15c lost ~3.5c in 20 of 23 non-sports series; one basket per edge source
DIV_SERIES = ["KXNATGASD", "KXCOPPERD", "KXGOLDD", "KXWTI", "KXBTCD", "KXETHD", "KXTRUMPAPPROVE", "KXTRUMPMENTION"]
FILL_WINDOW = 6  # hours an order rests


def get(path, **params):
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{url}: {err}")


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def mfee(p):
    """Kalshi maker fee per contract, rounded up to the cent."""
    return math.ceil(0.0175 * p * (1 - p) * 100) / 100


def fill_pnl(side, px, y, candles, t0):
    """P&L per contract if the resting order filled, else None.
    Filled only when a trade printed strictly through px within FILL_WINDOW hours of t0."""
    after = [c for c in candles if t0 < c["end_period_ts"] <= t0 + FILL_WINDOW * 3600]
    if side == "buy_yes":
        if not any((fnum(c["price"].get("low_dollars")) or 1) < px for c in after):
            return None
        return y - px - mfee(px)
    if not any((fnum(c["price"].get("high_dollars")) or 0) > px for c in after):
        return None
    return px - y - mfee(1 - px)


def mean(xs):
    return sum(xs) / len(xs)


def boot(xs, keys, n=1000):
    """95% CI of the mean, resampling whole events (markets in an event share an outcome)."""
    rng = random.Random(0)
    g = collections.defaultdict(list)
    for k, x in zip(keys, xs):
        g[k].append(x)
    gs, ms = list(g.values()), []
    for _ in range(n):
        pick = [x for grp in rng.choices(gs, k=len(gs)) for x in grp]
        ms.append(sum(pick) / len(pick))
    ms.sort()
    return ms[int(.025 * n)], ms[int(.975 * n)]
