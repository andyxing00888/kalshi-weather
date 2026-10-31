"""Forward paper trader for every rule in strategies.py. Reads public quotes; places no orders.

  python3 paper/trader.py log     hourly: for events ~H hours before close (H in HORIZONS),
                                  snapshot all buckets and record each rule's resting orders
  python3 paper/trader.py score   for settled logged orders: trade-through fill check + P&L
Files: paper/data/orders.csv (append-only), paper/data/scored.csv (one row per scored order).
"""
import collections, csv, os, sys, time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import get, fnum, fill_pnl, iso_ts, SERIES, ECON_SERIES, DIV_SERIES  # noqa: E402
from strategies import RULES, ECON_RULES, DIV_RULES  # noqa: E402

DATA = os.path.join(HERE, "data")
ORDERS = os.path.join(DATA, "orders.csv")
SCORED = os.path.join(DATA, "scored.csv")
HORIZONS = [30, 24, 18]
ECON_HORIZONS = [12, 6]
# (series, horizons, rules) for each group traded
DIV_HORIZONS = [24, 6]
BOOKS = [(SERIES, HORIZONS, RULES), (ECON_SERIES, ECON_HORIZONS, ECON_RULES), (DIV_SERIES, DIV_HORIZONS, DIV_RULES)]
OFIELDS = ["logged_utc", "log_ts", "hours_to_close", "rule", "H", "series", "event", "ticker",
           "side", "price", "bid", "ask", "mid"]
SFIELDS = OFIELDS + ["scored_utc", "result", "filled", "pnl"]


def read(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def append(path, fields, rows):
    os.makedirs(DATA, exist_ok=True)
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new:
            w.writeheader()
        w.writerows(rows)


def prev_mid(series, ticker, now):
    """Mid ~6h ago from hourly candles, or None."""
    cs = get(f"/series/{series}/markets/{ticker}/candlesticks",
             start_ts=int(now - 7 * 3600), end_ts=int(now - 5 * 3600), period_interval=60)["candlesticks"]
    for c in reversed(cs):
        b, a = fnum(c["yes_bid"].get("close_dollars")), fnum(c["yes_ask"].get("close_dollars"))
        if b is not None and a is not None and a > b:
            return (a + b) / 2
    return None


def log():
    now = time.time()
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    seen = {(r["rule"], r["H"], r["event"]) for r in read(ORDERS)}
    new, snaps = [], 0
    for s, horizons, rules in ((s, h, r) for ss, h, r in BOOKS for s in ss):
        events = collections.defaultdict(list)
        for m in get("/markets", series_ticker=s, status="open", limit=1000)["markets"]:
            events[m["event_ticker"]].append(m)
        for ev, ms in events.items():
            h = (iso_ts(ms[0]["close_time"]) - now) / 3600
            H = next((H for H in horizons if H - 1 <= h < H + 1.5), None)
            if H is None or all((r, str(H), ev) in seen for r in rules):
                continue
            key = lambda m: -1000.0 if m["strike_type"] == "less" else float(m.get("floor_strike") or -999)
            snap = []
            for m in sorted(ms, key=key):
                b, a = fnum(m.get("yes_bid_dollars")) or 0.0, fnum(m.get("yes_ask_dollars")) or 1.0
                snap.append(dict(ticker=m["ticker"], strike_type=m["strike_type"],
                                 floor=m.get("floor_strike"), cap=m.get("cap_strike"), bid=b, ask=a,
                                 mid=(a + b) / 2,  # only the weather rules (fade/follow_move) use prev_mid
                                 prev_mid=prev_mid(s, m["ticker"], now) if rules is RULES else None))
            snaps += 1
            for name, rule in rules.items():
                if (name, str(H), ev) in seen:
                    continue
                for t, side in rule(snap).items():
                    q = next(x for x in snap if x["ticker"] == t)
                    if not 0 < q["bid"] < q["ask"] < 1:
                        continue
                    new.append(dict(logged_utc=stamp, log_ts=int(now), hours_to_close=round(h, 2),
                                    rule=name, H=H, series=s, event=ev, ticker=t, side=side,
                                    price=q["bid"] if side == "buy_yes" else q["ask"],
                                    bid=q["bid"], ask=q["ask"], mid=round(q["mid"], 4)))
                # mark the rule as evaluated for this event even if it placed nothing
                seen.add((name, str(H), ev))
                new.append(dict(logged_utc=stamp, log_ts=int(now), hours_to_close=round(h, 2),
                                rule=name, H=H, series=s, event=ev, ticker="", side="none",
                                price="", bid="", ask="", mid=""))
        time.sleep(0.2)
    append(ORDERS, OFIELDS, new)
    print(f"{stamp} snapshots {snaps}, orders {sum(r['side'] != 'none' for r in new)}")


def score():
    done = {(r["rule"], r["H"], r["ticker"]) for r in read(SCORED)}
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    results, candles, rows = {}, {}, []
    for o in read(ORDERS):
        k = (o["rule"], o["H"], o["ticker"])
        if o["side"] == "none" or k in done:
            continue
        if o["ticker"] not in results:
            results[o["ticker"]] = get(f"/markets/{o['ticker']}")["market"].get("result")
        y = results[o["ticker"]]
        if y not in ("yes", "no"):
            continue
        ck = (o["ticker"], o["log_ts"])
        if ck not in candles:
            t0 = int(o["log_ts"])
            candles[ck] = get(f"/series/{o['series']}/markets/{o['ticker']}/candlesticks",
                              start_ts=t0, end_ts=t0 + 7 * 3600, period_interval=60)["candlesticks"]
        p = fill_pnl(o["side"], float(o["price"]), 1.0 if y == "yes" else 0.0, candles[ck], int(o["log_ts"]))
        rows.append(dict(o, scored_utc=stamp, result=y, filled=int(p is not None),
                         pnl="" if p is None else round(p, 4)))
        done.add(k)
    append(SCORED, SFIELDS, rows)
    print(f"{stamp} scored {len(rows)} orders, filled {sum(r['filled'] for r in rows)}")


if __name__ == "__main__":
    {"log": log, "score": score}[sys.argv[1]]()
