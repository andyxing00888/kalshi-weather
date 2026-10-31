"""Kalshi Liquidity Incentive Program: which rewards would a small two-sided quote actually earn?

Rules (help.kalshi.com/incentive-programs/liquidity-incentive-program), per one-second snapshot:
  a side counts only if its total resting size >= target; a snapshot pays only if both sides count
  reference price = walking down from the best bid, first level where cumulative size >= target/5
  order score     = size x (1 if at/above reference else discount^ticks_below)
  side share      = your score / all scores on that side;  snapshot score = yes share + no share
  reward          = period_reward x your snapshot scores / everyone's (2 per paying snapshot)
period_reward is in 1/10000 dollars.

Our hypothetical quote per side: Q contracts at the best bid (or at 1c if the side is empty, where a
lone order is its own reference price), plus filler bids at 1c to bring the side up to the target.
Filler scores ~0 but makes the snapshot pay; it costs 1c a contract and rarely fills.
Skipped when the quote would cross (yes bid + no bid > 0.99).

Usage: python3 lip.py [Q]     rank live programs by estimated $/day (default Q=300). Writes data/lip.csv.
       python3 lip.py watch      pick the watchlist (paper/data/lip_watch.json) from data/lip.csv
       python3 lip.py track      hourly forward simulation on the watchlist -> paper/data/lip_track.csv:
                                 re-quote at the best bid, earn share x reward for the hour, and log
                                 trades that printed through our prices since the last run as fills
       python3 lip.py report     rewards earned vs fill P&L on settled markets
One order-book snapshot per market: competition and depth change during the day.
"""
import csv, json, os, sys, time
from datetime import datetime
from kalshi.api import get, fnum, iso_ts
from kalshi.fees import mfee
from kalshi.paths import DATA, PAPER_DATA
from kalshi.store import append

WATCH = os.path.join(PAPER_DATA, "lip_watch.json")
TRACK = os.path.join(PAPER_DATA, "lip_track.csv")
N_WATCH, MAX_CAPITAL, MAX_VOL24 = 40, 300, 500
UNIT = 1e-4  # period_reward units -> dollars
FILL_PX = 0.01


def programs():
    out, cur = [], None
    while True:
        p = dict(status="active", limit=1000)
        if cur:
            p["cursor"] = cur
        d = get("/incentive_programs", **p)
        out += d["incentive_programs"]
        cur = d.get("next_cursor") or d.get("cursor")
        if not cur or not d["incentive_programs"]:
            return out


def scores(levels, target, disc):
    """levels = [(price, size, mine)] -> (total score, my score), or None if the side misses target."""
    levels = sorted(levels, key=lambda x: -x[0])
    if sum(s for _, s, _ in levels) < target - 1e-6:
        return None
    cum, ref = 0.0, levels[-1][0]
    for p, s, _ in levels:
        cum += s
        if cum >= target / 5:
            ref = p
            break
    sc = [(s * (1 if p >= ref - 1e-9 else disc ** round((ref - p) * 100)), mine) for p, s, mine in levels]
    return sum(x for x, _ in sc), sum(x for x, m in sc if m)


def plan(book, other_best, Q, target, disc):
    """Our orders on one side and the resulting (total, mine) score before and after we join."""
    best = book[0][0] if book else None
    px = best if best is not None else FILL_PX
    if px + (other_best if other_best is not None else 0) > 0.99:
        return None
    mine = [(px, Q, True)]
    fill = max(0.0, target - sum(s for _, s in book) - Q)
    if fill:
        mine.append((FILL_PX, fill, True))
    before = scores([(p, s, False) for p, s in book], target, disc)
    after = scores([(p, s, False) for p, s in book] + mine, target, disc)
    cost = sum(p * s for p, s, _ in mine)
    return dict(px=px, fill=fill, cost=cost, before=before is not None, total=after[0], mine=after[1])


def main(Q):
    now = time.time()
    progs = [p for p in programs() if iso_ts(p["start_date"]) <= now < iso_ts(p["end_date"])]
    for p in progs:
        days = max((iso_ts(p["end_date"]) - iso_ts(p["start_date"])) / 86400, 1 / 24)
        p["per_day"] = p["period_reward"] * UNIT / days
    progs.sort(key=lambda p: -p["per_day"])
    print(f"{len(progs)} live programs, headline ${sum(p['per_day'] for p in progs):,.0f}/day")
    mk, tick = {}, [p["market_ticker"] for p in progs]
    for i in range(0, len(tick), 100):
        for m in get("/markets", tickers=",".join(tick[i:i + 100]), limit=100)["markets"]:
            mk[m["ticker"]] = m
    rows = []
    for k, p in enumerate(progs):
        t = p["market_ticker"]
        m = mk.get(t, {})
        left = min(iso_ts(p["end_date"]), iso_ts(m["close_time"]) if m.get("close_time") else 1e12) - now
        if left < 6 * 3600:
            continue
        ob = get(f"/markets/{t}/orderbook")["orderbook_fp"]
        target, disc = fnum(p["target_size_fp"]), p["discount_factor_bps"] / 1e4
        book = {s: sorted(((float(a), float(b)) for a, b in ob.get(f"{s}_dollars") or []), reverse=True)
                for s in ("yes", "no")}
        best = {s: book[s][0][0] if book[s] else None for s in book}
        y = plan(book["yes"], best["no"], Q, target, disc)
        n = plan(book["no"], y["px"] if y else best["yes"], Q, target, disc)
        if not y or not n:
            continue
        share = (y["mine"] / y["total"] + n["mine"] / n["total"]) / 2
        rows.append(dict(ticker=t, per_day=round(p["per_day"], 2), est_day=round(p["per_day"] * share, 2),
                         share=round(share, 3), paying_now=int(y["before"] and n["before"]),
                         yes_px=y["px"], no_px=n["px"], yes_fill=round(y["fill"]), no_fill=round(n["fill"]),
                         depth_yes=round(sum(s for _, s in book["yes"])), depth_no=round(sum(s for _, s in book["no"])),
                         capital=round(y["cost"] + n["cost"], 2), days_left=round(left / 86400, 1),
                         vol24=fnum(m.get("volume_24h_fp")), kind=p["incentive_description"],
                         title=(m.get("title") or "")[:70]))
        if k % 500 == 499:
            print(f"  {k + 1} order books", flush=True)
        time.sleep(0.03)
    rows.sort(key=lambda r: -r["est_day"])
    with open(os.path.join(DATA, "lip.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\n{len(rows)} quotable programs (>6h left, no crossing), Q={Q:g}")
    for lab, sel in (("all", rows), ("paying now", [r for r in rows if r["paying_now"]]),
                     ("we'd switch on", [r for r in rows if not r["paying_now"]]),
                     ("no trades 24h", [r for r in rows if not r["vol24"]])):
        print(f"  {lab:15s} {len(sel):5d} programs  est ${sum(r['est_day'] for r in sel):8,.0f}/day  "
              f"capital ${sum(r['capital'] for r in sel):10,.0f}")
    print(f"\n{'est$/d':>7} {'pool':>6} {'share':>5} {'pay':>3} {'pxY':>5} {'pxN':>5} {'dY':>6} {'dN':>6} "
          f"{'cap$':>5} {'vol24':>6}  ticker | title")
    for r in rows[:40]:
        print(f"{r['est_day']:7.2f} {r['per_day']:6.1f} {r['share']:5.2f} {r['paying_now']:3d} {r['yes_px']:5.2f} "
              f"{r['no_px']:5.2f} {r['depth_yes']:6d} {r['depth_no']:6d} {r['capital']:5.0f} {r['vol24'] or 0:6.0f}  "
              f"{r['ticker']} | {r['title'][:38]}")


def watch():
    """Best est $/day among cheap, quiet markets; at most 3 per event so one outcome can't dominate."""
    rows = list(csv.DictReader(open(os.path.join(DATA, "lip.csv"))))
    picked, per_ev = [], {}
    for r in rows:
        ev = r["ticker"].rsplit("-", 1)[0]
        if float(r["capital"]) > MAX_CAPITAL or float(r["vol24"] or 0) > MAX_VOL24 or float(r["days_left"]) < 1:
            continue
        if per_ev.get(ev, 0) >= 3:
            continue
        per_ev[ev] = per_ev.get(ev, 0) + 1
        picked.append(r["ticker"])
        if len(picked) >= N_WATCH:
            break
    os.makedirs(os.path.dirname(WATCH), exist_ok=True)
    json.dump(dict(created=datetime.utcnow().isoformat(timespec="seconds") + "Z", tickers=picked), open(WATCH, "w"), indent=1)
    print(f"watching {len(picked)} markets, est ${sum(float(r['est_day']) for r in rows if r['ticker'] in picked):,.0f}/day")


def track(Q=300):
    tickers = json.load(open(WATCH))["tickers"]
    prev = {}
    if os.path.exists(TRACK):
        for r in csv.DictReader(open(TRACK)):
            if r["kind"] == "quote":
                prev[r["ticker"]] = r
    progs = {p["market_ticker"]: p for p in programs()}
    now = int(time.time())
    stamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    out = []
    for t in tickers:
        last = prev.get(t)
        # fills against the quote we left resting at the previous run: trades strictly through our price
        if last and last["yes_px"]:
            t0, ypx, npx = int(last["ts"]), float(last["yes_px"]), float(last["no_px"])
            for tr in get("/markets/trades", ticker=t, min_ts=t0, max_ts=now, limit=1000)["trades"]:
                yp, n = fnum(tr.get("yes_price_dollars")), fnum(tr.get("count_fp")) or 0
                if tr.get("taker_side") == "no" and yp < ypx - 1e-9:
                    out.append(dict(ts=now, utc=stamp, ticker=t, kind="fill", side="yes", price=ypx, size=n))
                elif tr.get("taker_side") == "yes" and yp > 1 - npx + 1e-9:
                    out.append(dict(ts=now, utc=stamp, ticker=t, kind="fill", side="no", price=npx, size=n))
        p = progs.get(t)
        row = dict(ts=now, utc=stamp, ticker=t, kind="quote", yes_px="", no_px="", share=0, reward=0,
                   hours=round((now - int(last["ts"])) / 3600, 2) if last else 0)
        if p:
            ob = get(f"/markets/{t}/orderbook")["orderbook_fp"]
            target, disc = fnum(p["target_size_fp"]), p["discount_factor_bps"] / 1e4
            book = {sd: sorted(((float(a), float(b)) for a, b in ob.get(f"{sd}_dollars") or []), reverse=True)
                    for sd in ("yes", "no")}
            y = plan(book["yes"], book["no"][0][0] if book["no"] else None, Q, target, disc)
            n = plan(book["no"], y["px"] if y else None, Q, target, disc) if y else None
            if y and n:
                days = max((iso_ts(p["end_date"]) - iso_ts(p["start_date"])) / 86400, 1 / 24)
                share = (y["mine"] / y["total"] + n["mine"] / n["total"]) / 2
                # reward for the hour just elapsed is credited at the share we held at its start
                held = float(last["share"]) if last else 0.0
                row.update(yes_px=y["px"], no_px=n["px"], share=round(share, 4),
                           reward=round(p["period_reward"] * UNIT / days * held * row["hours"] / 24, 4))
        out.append(row)
        time.sleep(0.05)
    append(TRACK, ["ts", "utc", "ticker", "kind", "yes_px", "no_px", "share", "reward",
                   "hours", "side", "price", "size"], out)
    q = [r for r in out if r["kind"] == "quote"]
    print(f"lip track: {len(q)} quotes, reward this run ${sum(r['reward'] for r in q):.2f}, "
          f"fills {sum(r['size'] for r in out if r['kind'] == 'fill'):g} contracts")


def report(Q=300, quiet=False):
    """Simulated rewards vs fill P&L. Returns the numbers for paper/report.py."""
    if not os.path.exists(TRACK):
        return None
    rows = list(csv.DictReader(open(TRACK)))
    reward = sum(float(r["reward"] or 0) for r in rows if r["kind"] == "quote")
    fills = [r for r in rows if r["kind"] == "fill"]
    res, pnl, open_n, done_n = {}, 0.0, 0.0, 0.0
    for r in fills:
        t = r["ticker"]
        if t not in res:
            res[t] = get(f"/markets/{t}")["market"].get("result")
        y = {"yes": 1.0, "no": 0.0}.get(res[t])
        n = min(float(r["size"]), Q)  # can't be filled for more than we rest
        if y is None:
            open_n += n
            continue
        done_n += n
        win = y if r["side"] == "yes" else 1 - y
        pnl += n * (win - float(r["price"]) - mfee(float(r["price"])))
    q = [r for r in rows if r["kind"] == "quote"]
    hours = sum(float(r["hours"] or 0) for r in q) / max(len({r["ticker"] for r in q}), 1)
    out = dict(runs=len({r["utc"] for r in q}), markets=len({r["ticker"] for r in q}), hours=hours,
               reward=reward, fill_pnl=pnl, settled=done_n, open=open_n, net=reward + pnl)
    if not quiet:
        print(f"{out['runs']} hourly runs over ~{hours:.0f}h, {out['markets']} markets")
        print(f"  simulated rewards ${reward:,.2f}")
        print(f"  settled fill P&L  ${pnl:,.2f} on {done_n:g} contracts ({open_n:g} still open)")
        print(f"  net ${out['net']:,.2f}")
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "watch":
        watch()
    elif cmd == "track":
        track()
    elif cmd == "report":
        report()
    else:
        main(float(cmd) if cmd else 300)
