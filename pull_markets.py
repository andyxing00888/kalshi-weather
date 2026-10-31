"""Pull settled Kalshi daily-high-temperature markets and hourly price candles.

Usage: python3 pull_markets.py [max_days_per_series]
Writes data/markets.csv and data/candles.csv (resumable; cached per market).
"""
import calendar, csv, json, os, sys, time, urllib.parse, urllib.request

BASE = "https://api.elections.kalshi.com/trade-api/v2"
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SERIES = ["KXHIGHNY", "KXHIGHCHI", "KXHIGHMIA", "KXHIGHAUS", "KXHIGHLAX",
          "KXHIGHDEN", "KXHIGHPHIL"]


def get(path, **params):
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            time.sleep(1.5 * (attempt + 1))
            err = e
    raise RuntimeError(f"{url}: {err}")


def settled_markets(series, max_events):
    out, cursor, events = [], None, set()
    while True:
        p = dict(series_ticker=series, status="settled", limit=1000)
        if cursor:
            p["cursor"] = cursor
        d = get("/markets", **p)
        for m in d["markets"]:
            events.add(m["event_ticker"])
            out.append(m)
        cursor = d.get("cursor")
        if not cursor or len(events) >= max_events:
            return out
        time.sleep(0.2)


def main():
    max_events = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    os.makedirs(DATA, exist_ok=True)
    mrows, crows = [], []
    for s in SERIES:
        ms = settled_markets(s, max_events)
        print(s, len(ms), "markets", flush=True)
        for m in ms:
            if m.get("result") not in ("yes", "no"):
                continue
            mrows.append(dict(
                series=s, event=m["event_ticker"], ticker=m["ticker"],
                strike_type=m.get("strike_type"), floor=m.get("floor_strike"),
                cap=m.get("cap_strike"), result=m["result"],
                value=m.get("expiration_value"), open_time=m["open_time"],
                close_time=m["close_time"], volume=m.get("volume_fp"),
                title=m.get("yes_sub_title")))
            cp = os.path.join(DATA, "cache", m["ticker"] + ".json")
            if os.path.exists(cp):
                cs = json.load(open(cp))
            else:
                t0 = calendar.timegm(time.strptime(m["open_time"][:19], "%Y-%m-%dT%H:%M:%S"))
                t1 = calendar.timegm(time.strptime(m["close_time"][:19], "%Y-%m-%dT%H:%M:%S"))
                cs = get(f"/series/{s}/markets/{m['ticker']}/candlesticks",
                         start_ts=t0, end_ts=t1, period_interval=60)["candlesticks"]
                os.makedirs(os.path.dirname(cp), exist_ok=True)
                json.dump(cs, open(cp, "w"))
                time.sleep(0.1)
            for c in cs:
                g = lambda k, f: (c.get(k) or {}).get(f)
                crows.append(dict(
                    ticker=m["ticker"], end_ts=c["end_period_ts"],
                    price_close=g("price", "close_dollars"),
                    bid_close=g("yes_bid", "close_dollars"),
                    ask_close=g("yes_ask", "close_dollars"),
                    volume=c.get("volume_fp")))
    for name, rows in (("markets", mrows), ("candles", crows)):
        with open(os.path.join(DATA, f"{name}.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print("wrote", name, len(rows))


if __name__ == "__main__":
    main()
