"""Gas test: does lagged RBOB wholesale gasoline predict the next AAA national average better than Kalshi?

Needs data/econ_markets.csv, econ_candles.csv (see econ.py). Downloads data/rbob.json (Yahoo chart
JSON for RB=F, 1y daily) if missing; REFRESH=1 re-downloads. Usage: python3 -m legacy.gas [hours_before_close ...]
Model, walk-forward per event day D (resolves on AAA's price for D):
  dAAA_D = a + b * (RBOB 5-session change, using closes dated <= D-LAG), OLS on the prior 40 days,
  outcome distribution = prediction + prior residuals. Trade at quote when edge > EDGE, taker fee.
"""
import collections, json, os, sys, urllib.request
from datetime import date, datetime, timedelta, timezone
from kalshi.api import edate, fnum, iso_ts
from kalshi.fees import fee
from kalshi.stats import boot, mean
from legacy.analyze import rd
from legacy.econ import quote_at, value, yes_if

EDGE = float(os.environ.get("EDGE", 0.05))
LAG = int(os.environ.get("LAG", 1))  # 1: D-1 RBOB settle is known by the evening before close


RBOB_URL = "https://query1.finance.yahoo.com/v8/finance/chart/RB=F?range=1y&interval=1d"


def rbob():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rbob.json")
    if not os.path.exists(path) or os.environ.get("REFRESH"):
        req = urllib.request.Request(RBOB_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r, open(path, "wb") as f:
            f.write(r.read())
    d = json.load(open(path))["chart"]["result"][0]
    return sorted((datetime.fromtimestamp(t, timezone.utc).date(), c)
                  for t, c in zip(d["timestamp"], d["indicators"]["quote"][0]["close"]) if c)


def feature(rb, D):
    cut = D - timedelta(days=LAG)
    xs = [c for d, c in rb if d <= cut]
    return xs[-1] - xs[-6] if len(xs) >= 6 else None


def ols(xy):
    mx, my = mean([x for x, _ in xy]), mean([y for _, y in xy])
    sxx = sum((x - mx) ** 2 for x, _ in xy)
    b = sum((x - mx) * (y - my) for x, y in xy) / sxx if sxx else 0
    return my - b * mx, b


def main():
    hours = [float(a) for a in sys.argv[1:]] or [2, 6, 12]
    rb = rbob()
    ms = [m for m in rd("econ_markets.csv") if m["series"] == "KXAAAGASD" and m["result"] in ("yes", "no")]
    candles = collections.defaultdict(list)
    for c in rd("econ_candles.csv"):
        candles[c["ticker"]].append(c)
    ev = collections.defaultdict(list)
    for m in ms:
        ev[date.fromisoformat(edate(m["event"]))].append(m)
    days = sorted(ev)
    aaa = {D: value(ev[D][0]) for D in days}

    rows = []  # (D, x, dy)
    for D in days:
        P = D - timedelta(days=1)
        x = feature(rb, D)
        if P in aaa and x is not None:
            rows.append((D, x, aaa[D] - aaa[P]))
    xs, ys = [r[1] for r in rows], [r[2] for r in rows]
    mx, my = mean(xs), mean(ys)
    corr = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / (sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys)) ** .5
    print(f"days with feature {len(rows)}; corr(RBOB 5-session change, next AAA change) = {corr:+.2f}")
    print(f"AAA daily change: mean {my * 100:+.2f}¢ sd {mean([(y - my) ** 2 for y in ys]) ** .5 * 100:.2f}¢")

    for H in hours:
        recs, brier = [], []
        for k, (D, x, dy) in enumerate(rows):
            hist = rows[max(0, k - 40):k]
            if len(hist) < 20:
                continue
            a, b = ols([(r[1], r[2]) for r in hist])
            res = [r[2] - (a + b * r[1]) for r in hist]
            prev = aaa[D - timedelta(days=1)]
            for m in ev[D]:
                q = quote_at(candles[m["ticker"]], iso_ts(m["close_time"]) - H * 3600)
                if not q:
                    continue
                outs = [yes_if(m, prev + a + b * x + e) for e in res]
                p = (sum(outs) + 0.5) / (len(outs) + 1)
                y = 1.0 if m["result"] == "yes" else 0.0
                ask, bid = fnum(q["ask_close"]), fnum(q["bid_close"])
                mid = (ask + bid) / 2
                brier.append(((p - y) ** 2, (mid - y) ** 2, m["event"]))
                if 0 < ask < 1 and p - ask > EDGE:
                    recs.append((m["event"], y - ask - fee(ask)))
                elif 0 < bid < 1 and bid - p > EDGE:
                    recs.append((m["event"], bid - y - fee(1 - bid)))
        d = [u - v for u, v, _ in brier]
        lo, hi = boot(d, [e for *_, e in brier])
        print(f"-- {H:g}h before close: Brier model {mean([u for u, _, _ in brier]):.4f} market mid "
              f"{mean([v for _, v, _ in brier]):.4f} diff {mean(d):+.4f} [{lo:+.4f},{hi:+.4f}]")
        if recs:
            p = [x for _, x in recs]
            lo, hi = boot(p, [e for e, _ in recs])
            print(f"   trades edge>{EDGE}: n={len(p)} events={len({e for e, _ in recs})} "
                  f"pnl/contract {mean(p):+.4f} [{lo:+.4f},{hi:+.4f}]")


if __name__ == "__main__":
    main()
