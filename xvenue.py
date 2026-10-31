"""Kalshi vs Polymarket on the same sports games (two-way moneylines).

Games are matched exactly: Kalshi KXNBAGAME-26NOV02MIALAL-MIA <-> Polymarket slug nba-mia-lal-2026-11-02.
For each team T:
  arb      buy T on one venue + the other team on the other; payoff 1 whoever wins.
           Kalshi taker fee ceil(0.07 p(1-p)) to the cent, Polymarket 0.05 p(1-p) (sports, no rounding).
  signal   Kalshi quote vs Polymarket mid (the deeper book used as a free model).

Usage: python3 xvenue.py          print matched games, gaps and arbs
       python3 xvenue.py log      also append every matched quote to paper/data/xvenue.csv
Polymarket is read-only here: it is not open to US persons except via Polymarket US.
Resolution rules can differ (postponements, overtime); check both before trading an arb.
"""
import csv, json, os, re, sys, time, urllib.request
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper"))
from common import get, fnum, fee, iso_ts  # noqa: E402

GAMMA = "https://gamma-api.polymarket.com"
LEAGUES = {"nba": "KXNBAGAME", "nfl": "KXNFLGAME", "nhl": "KXNHLGAME", "cfb": "KXNCAAFGAME",
           "cbb": "KXNCAAMBGAME", "mlb": "KXMLBGAME", "wnba": "KXWNBAGAME"}
POLY_FEE = 0.05
MAX_SPREAD = 0.03
LOG_HOURS = 48  # log only games starting within this many hours
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper", "data", "xvenue.csv")
FIELDS = ["utc", "league", "game", "team", "start", "k_bid", "k_ask", "k_bid_size", "k_ask_size",
          "p_bid", "p_ask", "p_liq", "k_ticker", "p_token"]


def pget(path):
    for attempt in range(5):
        try:
            req = urllib.request.Request(GAMMA + path, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{path}: {err}")


def pfee(p):
    return POLY_FEE * p * (1 - p)


def poly_games():
    """{(league, date, frozenset(codes)): {quotes: {code: (bid, ask, token)}, start, liq, slug}}."""
    out = {}
    now = datetime.now(timezone.utc)
    win = f"&end_date_min={now:%Y-%m-%dT%H:%M:%SZ}&end_date_max={now + timedelta(days=10):%Y-%m-%dT%H:%M:%SZ}"
    slug_re = re.compile(r"^([a-z0-9]+)-([a-z0-9]+)-([a-z0-9]+)-(\d{4}-\d{2}-\d{2})$")
    for lg in LEAGUES:
        off = 0
        while off < 2000:  # gamma rejects larger offsets
            evs = pget(f"/events?active=true&closed=false&tag_slug={lg}&limit=100&offset={off}" + win)
            for e in evs:
                m = slug_re.match(e["slug"])
                if not m or m.group(1) != lg:
                    continue
                _, a, b, date = m.groups()
                ml = [x for x in e.get("markets", []) if x.get("sportsMarketType") == "moneyline"
                      and len(json.loads(x.get("outcomes") or "[]")) == 2 and not x.get("closed")]
                if len(ml) != 1:
                    continue
                x = ml[0]
                bid, ask = fnum(x.get("bestBid")), fnum(x.get("bestAsk"))
                toks = json.loads(x.get("clobTokenIds") or "[]")
                if bid is None or ask is None or len(toks) != 2:
                    continue
                # first outcome is the first team in the slug; the second side is the mirror quote
                out[lg, date, frozenset((a, b))] = dict(
                    quotes={a: (bid, ask, toks[0]), b: (1 - ask, 1 - bid, toks[1])},
                    start=e.get("startTime") or x.get("gameStartTime") or e.get("endDate"),
                    liq=fnum(x.get("liquidityClob") or x.get("liquidity")), slug=e["slug"])
            if len(evs) < 100:
                break
            off += 100
    return out


def kalshi_games(series):
    """{(date, frozenset(codes)): {code: market}} for open game events."""
    out, cursor = {}, None
    while True:
        p = dict(series_ticker=series, status="open", limit=200, with_nested_markets="true")
        if cursor:
            p["cursor"] = cursor
        d = get("/events", **p)
        for e in d["events"]:
            ms = e.get("markets") or []
            if len(ms) != 2:
                continue
            tail = e["event_ticker"].split("-")[1]
            date = datetime.strptime(tail[:7], "%y%b%d").strftime("%Y-%m-%d")
            codes = {m["ticker"].rsplit("-", 1)[1].lower(): m for m in ms}
            out[date, frozenset(codes)] = codes
        cursor = d.get("cursor")
        if not cursor or not d["events"]:
            return out


def main():
    log = len(sys.argv) > 1 and sys.argv[1] == "log"
    poly = poly_games()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows, arbs, gaps = [], [], []
    for lg, series in LEAGUES.items():
        kal = kalshi_games(series)
        pk = {(d, c): v for (l, d, c), v in poly.items() if l == lg}
        both = set(kal) & set(pk)
        print(f"{lg}: kalshi {len(kal)} games, polymarket {len(pk)}, matched {len(both)}")
        for key in sorted(both):
            date, codes = key
            pg = pk[key]
            for team, m in kal[key].items():
                kb, ka = fnum(m.get("yes_bid_dollars")), fnum(m.get("yes_ask_dollars"))
                pb, pa, tok = pg["quotes"][team]
                rows.append(dict(utc=now, league=lg, game=m["event_ticker"], team=team, start=pg["start"],
                                 k_bid=kb, k_ask=ka, k_bid_size=m.get("yes_bid_size_fp"),
                                 k_ask_size=m.get("yes_ask_size_fp"), p_bid=pb, p_ask=pa, p_liq=pg["liq"],
                                 k_ticker=m["ticker"], p_token=tok))
                if not (ka and 0 < ka < 1 and 0 < pb < 1):
                    continue
                other = 1 - pb  # buy the other team on Polymarket at its ask
                edge = 1 - ka - other - fee(ka) - pfee(other)
                arbs.append((edge, f"buy {team.upper()} kalshi @{ka:.2f} + other team poly @{other:.3f}", m["ticker"], pg["slug"]))
                if kb and 0 < kb < 1 and 0 < pa < 1:
                    # buy T on Polymarket, buy NO T (= other team) on Kalshi at 1 - kb
                    edge2 = 1 - pa - (1 - kb) - pfee(pa) - fee(1 - kb)
                    arbs.append((edge2, f"buy {team.upper()} poly @{pa:.3f} + NO kalshi @{1 - kb:.2f}", m["ticker"], pg["slug"]))
                    pm = (pb + pa) / 2
                    if pa - pb <= MAX_SPREAD:  # a wide Polymarket book says nothing about fair value
                        gaps.append((max(pm - ka - fee(ka), kb - pm - fee(1 - kb)), team, m["ticker"], kb, ka, pb, pa))
    hits = sorted((a for a in arbs if a[0] > 0), reverse=True)
    print(f"\n{len(rows)} matched team quotes, {len(arbs)} two-venue baskets, {len(hits)} arbs after fees")
    for edge, desc, kt, slug in hits[:15]:
        print(f"  ARB {edge:+.3f}  {desc}  [{kt} | {slug}]")
    print(f"\nlargest Kalshi-vs-Polymarket-mid gaps after Kalshi taker fee (poly spread <= {MAX_SPREAD}):")
    for g, team, kt, kb, ka, pb, pa in sorted(gaps, reverse=True)[:15]:
        print(f"  {g:+.3f}  {kt:38s} kalshi {kb:.2f}/{ka:.2f}  poly {pb:.3f}/{pa:.3f}")
    soon = datetime.now(timezone.utc) + timedelta(hours=LOG_HOURS)
    rows = [r for r in rows if r["start"] and iso_ts(r["start"]) <= soon.timestamp()]
    if log and rows:
        new = not os.path.exists(LOG)
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            if new:
                w.writeheader()
            w.writerows(rows)
        print(f"logged {len(rows)} rows to {LOG}")


if __name__ == "__main__":
    main()
