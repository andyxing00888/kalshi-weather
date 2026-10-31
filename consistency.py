"""Cross-series arbitrage inside Kalshi: S&P / Nasdaq daily close listed three ways.

  range  KXINX / KXNASDAQ100       buckets [K, K+w) plus two tails
  above  KXINXU / KXNASDAQ100U     X >= K ladder (4pm event only)
  updown KXINXDUD / KXNASDAQDUD    X > previous close
All three settle on the same 4pm close, so they must agree. Every check below is a basket
of taker buys whose payoff is the same in every outcome; it is an arb if cost + fees < payoff.

  1) ladder   buy YES above(K_lo) + NO above(K_hi)                       payoff >= 1
  2) range    buy YES on buckets in [K1,K2) + NO above(K1) + YES above(K2)  payoff 1
              buy NO on those buckets + YES above(K1) + NO above(K2)     payoff n+1
  3) updown   YES updown + NO above(K just over D); YES above(K at/under D) + NO updown
  4) dutch    YES on every bucket (payoff 1); NO on every bucket (payoff n-1)

Usage: python3 consistency.py pull [days]   cache settled 4pm events + hourly candles
       python3 consistency.py               backtest every candle hour on cached data
       python3 consistency.py rv            relative value: thin series priced off the above-ladder
       python3 consistency.py live          check current quotes on open events (with sizes)
Hourly candle bid/ask are close-of-hour snapshots; any hit must be confirmed live.
"""
import collections, csv, json, math, os, sys, time
from datetime import datetime, timedelta, timezone
from analyze import fee
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper"))
from common import get, fnum  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CACHE = os.path.join(DATA, "cache")
MKTS = os.path.join(DATA, "cons_markets.json")
LIVE_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper", "data", "consistency.csv")
# name: (range, above, updown, keep above strikes on this grid; None keeps all)
FAMILIES = {"SPX": ("KXINX", "KXINXU", "KXINXDUD", None),
            "NDX": ("KXNASDAQ100", "KXNASDAQ100U", "KXNASDAQDUD", 100)}
INF = float("inf")
RV_EDGE = float(os.environ.get("EDGE", 0.03))
RV_MAX_SPREAD = 0.10   # ladder strikes wider than this are not used as the model
RV_MAX_GAP = 30       # max index points between the two strikes interpolated
RV_HOURS = [1, 2, 4, 6]
PAPER_H, PAPER_EDGES = 6, (0.03, 0.06)  # forward-tested in paper/data/orders.csv


def iso_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def settled_events(series, since):
    out, cursor = [], None
    while True:
        p = dict(series_ticker=series, status="settled", limit=200)
        if cursor:
            p["cursor"] = cursor
        d = get("/events", **p)
        evs = [e["event_ticker"] for e in d["events"] if e["event_ticker"].endswith("H1600")]
        out += [e for e in evs if datetime.strptime(e.split("-")[1][:7], "%y%b%d") >= since]
        cursor = d.get("cursor")
        oldest = d["events"][-1]["event_ticker"].split("-")[1][:7] if d["events"] else None
        if not cursor or (oldest and datetime.strptime(oldest, "%y%b%d") < since):
            return out


def candles(series, m):
    cp = os.path.join(CACHE, m["ticker"] + ".json")
    if os.path.exists(cp):
        return json.load(open(cp))
    cs = get(f"/series/{series}/markets/{m['ticker']}/candlesticks", start_ts=int(iso_ts(m["open_time"])),
             end_ts=int(iso_ts(m["close_time"])), period_interval=60)["candlesticks"]
    os.makedirs(CACHE, exist_ok=True)
    json.dump(cs, open(cp, "w"))
    time.sleep(0.05)
    return cs


def keep(m, role, grid, dud):
    """Nasdaq above-ladder has 200 strikes; keep bucket edges and the two around the updown strike."""
    if role != "above" or grid is None:
        return True
    k = m["floor_strike"]
    return k % grid == 0 or (dud is not None and abs(k - dud) <= 10)


def pull(days):
    since = datetime.now() - timedelta(days=days)
    out = json.load(open(MKTS)) if os.path.exists(MKTS) else {}
    for fam, (rs, ab, ud, grid) in FAMILIES.items():
        for e in settled_events(rs, since):
            date = e.split("-", 1)[1]
            if f"{fam}-{date}" in out:
                continue
            legs = {}
            for role, s in (("updown", ud), ("range", rs), ("above", ab)):
                ms = get("/markets", event_ticker=f"{s}-{date}", limit=500)["markets"]
                dud = legs["updown"][0]["floor_strike"] if legs.get("updown") else None
                legs[role] = [dict(ticker=m["ticker"], series=s, strike_type=m["strike_type"],
                                   floor_strike=m.get("floor_strike"), cap_strike=m.get("cap_strike"),
                                   result=m["result"], value=m.get("expiration_value"),
                                   open_time=m["open_time"], close_time=m["close_time"])
                              for m in ms if keep(m, role, grid, dud)]
            n = 0
            for role in legs:
                for m in legs[role]:
                    candles(m["series"], m)
                    n += 1
            out[f"{fam}-{date}"] = legs
            json.dump(out, open(MKTS, "w"))
            print(fam, date, {r: len(v) for r, v in legs.items()}, flush=True)


def layout(legs):
    """Bucket edges as numbers. Strikes on the grid are rounded to integers (7324.9999 -> 7325)."""
    buckets = []
    for m in legs["range"]:
        st, f, c = m["strike_type"], m.get("floor_strike"), m.get("cap_strike")
        lo = -INF if st == "less" else round(f)
        hi = INF if st == "greater" else round(c)
        buckets.append((lo, hi, m["ticker"]))
    buckets.sort()
    above = sorted((round(m["floor_strike"]), m["ticker"]) for m in legs["above"])
    ud = [(m["floor_strike"], m["ticker"]) for m in legs.get("updown", [])]
    return buckets, above, ud[0] if ud else None


def yes(q, t):
    """(cost, fee) to buy YES at the ask, or None if no offer."""
    b, a = q.get(t, (None, None))[:2]
    return (a, fee(a)) if a is not None and 0 < a < 1 else None


def no(q, t):
    b, a = q.get(t, (None, None))[:2]
    return (1 - b, fee(1 - b)) if b is not None and 0 < b < 1 else None


def basket(legs, payoff):
    """Edge after fees, raw edge, and the legs; None if any leg has no quote."""
    if any(x is None for _, x in legs):
        return None
    cost = sum(x[0] for _, x in legs)
    fees = sum(x[1] for _, x in legs)
    return payoff - cost - fees, payoff - cost, [t for t, _ in legs]


def checks(lay, q):
    """Yield (kind, edge_after_fees, raw_edge, tickers) for every basket with full quotes."""
    buckets, above, ud = lay
    for (k1, t1), (k2, t2) in zip(above, above[1:]):
        r = basket([(t1, yes(q, t1)), (t2, no(q, t2))], 1)
        if r:
            yield ("ladder",) + r
    edges = {k: t for k, t in above}
    edges[-INF] = edges[INF] = None
    lows = [lo for lo, _, _ in buckets]
    for i, lo in enumerate(lows):
        if lo not in edges:
            continue
        for j in range(i, len(buckets)):
            hi = buckets[j][1]
            if hi not in edges or (lo == -INF and hi == INF):
                continue
            inner = [b[2] for b in buckets[i:j + 1]]
            ta, tb = edges[lo], edges[hi]
            a = [(t, yes(q, t)) for t in inner] + ([(ta, no(q, ta))] if ta else []) + ([(tb, yes(q, tb))] if tb else [])
            b = [(t, no(q, t)) for t in inner] + ([(ta, yes(q, ta))] if ta else []) + ([(tb, no(q, tb))] if tb else [])
            extra = (ta is not None) + (tb is not None)
            for kind, legs, pay in (("range_yes", a, 1), ("range_no", b, len(inner) - 1 + extra)):
                r = basket(legs, pay)
                if r:
                    yield (kind,) + r
    if ud:
        d, td = ud
        dn = [x for x in above if x[0] <= d]
        up = [x for x in above if x[0] > d]
        if up:
            r = basket([(td, yes(q, td)), (up[0][1], no(q, up[0][1]))], 1)
            if r:
                yield ("updown",) + r
        if dn:
            r = basket([(dn[-1][1], yes(q, dn[-1][1])), (td, no(q, td))], 1)
            if r:
                yield ("updown",) + r
    tick = [b[2] for b in buckets]
    for kind, f, pay in (("dutch_yes", yes, 1), ("dutch_no", no, len(tick) - 1)):
        r = basket([(t, f(q, t)) for t in tick], pay)
        if r:
            yield (kind,) + r


def backtest():
    data = json.load(open(MKTS))
    stats = collections.defaultdict(lambda: dict(n=0, hours=set(), raw_pos=0, hits=[], best=-9))
    for key, legs in sorted(data.items()):
        lay = layout(legs)
        byt = collections.defaultdict(dict)
        close = iso_ts(legs["range"][0]["close_time"])
        for role in legs:
            for m in legs[role]:
                for c in json.load(open(os.path.join(CACHE, m["ticker"] + ".json"))):
                    b, a = fnum(c["yes_bid"].get("close_dollars")), fnum(c["yes_ask"].get("close_dollars"))
                    byt[c["end_period_ts"]][m["ticker"]] = (b, a)
        fam = key.split("-")[0]
        for t, q in byt.items():
            if t > close:
                continue
            for kind, edge, raw, tickers in checks(lay, q):
                s = stats[fam, kind]
                s["n"] += 1
                s["hours"].add((key, t))
                s["raw_pos"] += raw > 0
                s["best"] = max(s["best"], edge)
                if edge > 0:
                    s["hits"].append((edge, key, t, tickers))
    print(f"{len(data)} event-days: {collections.Counter(k.split('-')[0] for k in data)}")
    for (fam, kind), s in sorted(stats.items()):
        hits = s["hits"]
        print(f"{fam} {kind:9s} baskets={s['n']:7d} hours={len(s['hours']):5d} raw>0={s['raw_pos']:6d} "
              f"after-fee hits={len(hits):5d} in {len({h[1] for h in hits})} days  best={s['best']:+.3f}")
        for edge, key, t, tickers in sorted(hits, reverse=True)[:3]:
            hrs = (iso_ts(data[key]["range"][0]["close_time"]) - t) / 3600
            print(f"    {edge:+.3f} {key} {hrs:.0f}h before close: {' '.join(tickers)[:160]}")


def fair_above(above, q, x):
    """P(close >= x) from the above-ladder mids, linear between the nearest quoted strikes."""
    if x == -INF:
        return 1.0
    if x == INF:
        return 0.0
    pts = []
    for k, t in above:
        b, a = q.get(t, (None, None))
        if b is not None and a is not None and 0 < a <= 1 and a - b <= RV_MAX_SPREAD:
            pts.append((k, (a + b) / 2))
    lo = [p for p in pts if p[0] <= x]
    hi = [p for p in pts if p[0] >= x]
    if not lo or not hi:
        return None
    (k0, p0), (k1, p1) = lo[-1], hi[0]
    if k1 - k0 > RV_MAX_GAP:
        return None
    return p0 if k1 == k0 else p0 + (p1 - p0) * (x - k0) / (k1 - k0)


def maker_quotes(fair, b, a, edge):
    """Resting orders `edge` either side of fair, never crossing the book."""
    out = []
    px = math.floor((fair - edge) * 100) / 100
    if 0.01 <= px < a:
        out.append(("buy_yes", px))
    px = math.ceil((fair + edge) * 100) / 100
    if b < px <= 0.99:
        out.append(("sell_yes", px))
    return out


def paper_rv(stamp):
    """Forward-test the updown maker rule: at ~6h before close, rest quotes around the ladder-implied
    P(close > D). Rows go into the trader's orders.csv so trader.py score fills and scores them."""
    from trader import read, append, ORDERS, OFIELDS
    seen = {(r["rule"], r["H"], r["event"]) for r in read(ORDERS)}
    now, new = time.time(), []
    for fam, (rs, ab, ud, grid) in FAMILIES.items():
        for m in get("/markets", series_ticker=ud, status="open", limit=50)["markets"]:
            h = (iso_ts(m["close_time"]) - now) / 3600
            if not PAPER_H - 1 <= h < PAPER_H + 1.5:
                continue
            ev = m["event_ticker"]
            above = get("/markets", event_ticker=ev.replace(ud, ab, 1), limit=500)["markets"]
            q = {x["ticker"]: (fnum(x.get("yes_bid_dollars")), fnum(x.get("yes_ask_dollars"))) for x in above}
            fair = fair_above(sorted((round(x["floor_strike"]), x["ticker"]) for x in above), q, m["floor_strike"])
            b, a = fnum(m.get("yes_bid_dollars")) or 0.0, fnum(m.get("yes_ask_dollars")) or 1.0
            for edge in PAPER_EDGES:
                rule = f"rv_updown_{round(edge * 100)}c"
                if (rule, str(PAPER_H), ev) in seen:
                    continue
                base = dict(logged_utc=stamp, log_ts=int(now), hours_to_close=round(h, 2), rule=rule,
                            H=PAPER_H, series=ud, event=ev, bid=b, ask=a,
                            mid="" if fair is None else round(fair, 4))  # mid column holds the model fair
                for side, px in maker_quotes(fair, b, a, edge) if fair is not None else []:
                    new.append(dict(base, ticker=m["ticker"], side=side, price=px))
                new.append(dict(base, ticker="", side="none", price=""))
    append(ORDERS, OFIELDS, new)
    print(f"rv paper orders: {sum(r['side'] != 'none' for r in new)}")


def rv():
    """Relative value: price updown and range buckets off the deep above-ladder, trade the thin series.
    taker: buy at the quote when fair beats it by RV_EDGE after taker fee.
    maker: rest a bid RV_EDGE under fair (or offer above), filled only on trade-through within 6h."""
    from common import fill_pnl, boot, mean
    data = json.load(open(MKTS))
    res = collections.defaultdict(list)
    for key, legs in sorted(data.items()):
        fam = key.split("-")[0]
        buckets, above, ud = layout(legs)
        close = iso_ts(legs["range"][0]["close_time"])
        raw, byt = {}, collections.defaultdict(dict)
        for role in legs:
            for m in legs[role]:
                raw[m["ticker"]] = json.load(open(os.path.join(CACHE, m["ticker"] + ".json")))
                for c in raw[m["ticker"]]:
                    byt[c["end_period_ts"]][m["ticker"]] = (fnum(c["yes_bid"].get("close_dollars")),
                                                            fnum(c["yes_ask"].get("close_dollars")))
        result = {m["ticker"]: 1.0 if m["result"] == "yes" else 0.0 for r in legs for m in legs[r]}
        # (kind, ticker, fair(q)): updown is X > D, buckets are [lo, hi)
        targets = [("range", t, (lambda q, lo=lo, hi=hi: (lambda a, b: None if a is None or b is None else a - b)(
            fair_above(above, q, lo), fair_above(above, q, hi)))) for lo, hi, t in buckets]
        if ud:
            targets.append(("updown", ud[1], lambda q, d=ud[0]: fair_above(above, q, d)))
        for H in RV_HOURS:
            t0 = int(close - H * 3600)
            q = byt.get(t0)
            if not q:
                continue
            for kind, tk, f in targets:
                fair = f(q)
                b, a = q.get(tk, (None, None))
                if fair is None or b is None or a is None:
                    continue
                y = result[tk]
                if 0 < a < 1 and fair - a - fee(a) > RV_EDGE:
                    res[fam, kind, "taker", H].append((key, y - a - fee(a)))
                if 0 < b < 1 and b - fair - fee(1 - b) > RV_EDGE:
                    res[fam, kind, "taker", H].append((key, b - y - fee(1 - b)))
                for side, px in maker_quotes(fair, b, a, RV_EDGE):
                    p = fill_pnl(side, px, y, raw[tk], t0)
                    if p is not None:
                        res[fam, kind, "maker", H].append((key, p))
    print(f"relative value off the above-ladder, edge>{RV_EDGE}, ladder spread<={RV_MAX_SPREAD}")
    for k in sorted(res):
        xs = res[k]
        pn = [x for _, x in xs]
        lo, hi = boot(pn, [e for e, _ in xs])
        print(f"  {k[0]} {k[1]:6s} {k[2]} {k[3]}h: n={len(pn):4d} days={len({e for e, _ in xs}):3d} "
              f"pnl/contract {mean(pn):+.4f} [{lo:+.4f},{hi:+.4f}]")


def live(log=False):
    rows, now = [], datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for fam, (rs, ab, ud, grid) in FAMILIES.items():
        evs = get("/events", series_ticker=rs, status="open", limit=50)["events"]
        for e in sorted(x["event_ticker"] for x in evs if x["event_ticker"].endswith("H1600")):
            date = e.split("-", 1)[1]
            legs, q, size = {}, {}, {}
            for role, s in (("updown", ud), ("range", rs), ("above", ab)):
                ms = get("/markets", event_ticker=f"{s}-{date}", limit=500)["markets"]
                legs[role] = ms
                for m in ms:
                    q[m["ticker"]] = (fnum(m.get("yes_bid_dollars")), fnum(m.get("yes_ask_dollars")))
                    size[m["ticker"]] = (fnum(m.get("yes_bid_size_fp")), fnum(m.get("yes_ask_size_fp")))
            if not legs["range"] or not legs["above"]:
                continue
            res = list(checks(layout(legs), q))
            hits = sorted((r for r in res if r[1] > 0), key=lambda r: -r[1])
            best = max(res, key=lambda r: r[1]) if res else None
            print(f"{fam} {date}: {len(res)} baskets, {len(hits)} arbs" +
                  (f", best {best[0]} {best[1]:+.3f} (raw {best[2]:+.3f})" if best else ""))
            for kind, edge, raw, tickers in hits[:10]:
                depth = min(min(x or 0 for x in size[t]) for t in tickers)
                print(f"   ARB {kind} {edge:+.3f}/set, min depth {depth:g}: {' '.join(tickers)}")
            # one row per event per run (best basket), plus every arb
            for kind, edge, raw, tickers in ([best] if best and not hits else []) + hits:
                rows.append(dict(utc=now, family=fam, event=date, kind=kind, edge=round(edge, 4),
                                 raw=round(raw, 4), arb=int(edge > 0),
                                 depth=min(min(x or 0 for x in size[t]) for t in tickers), legs=" ".join(tickers)))
    if log:
        paper_rv(now)
    if log and rows:
        new = not os.path.exists(LIVE_LOG)
        with open(LIVE_LOG, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            if new:
                w.writeheader()
            w.writerows(rows)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "backtest"
    if cmd == "pull":
        pull(int(sys.argv[2]) if len(sys.argv) > 2 else 60)
    elif cmd == "rv":
        rv()
    elif cmd in ("live", "log"):
        live(log=cmd == "log")
    else:
        backtest()
