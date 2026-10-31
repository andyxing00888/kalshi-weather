"""Daily paper-trading report.

  python3 paper/report.py [YYYY-MM-DD]   (default: today UTC)
Writes paper/reports/<date>.md (that day's settlements + cumulative stats) and paper/README.md
(cumulative scoreboard, links to recent reports).
"""
import collections, os, sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import boot, mean  # noqa: E402
from strategies import RULES  # noqa: E402
from trader import read, ORDERS, SCORED  # noqa: E402

REPORTS = os.path.join(HERE, "reports")
MIN_FILLS = 100  # fills before a verdict


def money(x):
    return f"{x * 100:+.1f}¢"


def verdict(n, lo, hi):
    if n < MIN_FILLS:
        return f"collecting ({n}/{MIN_FILLS})"
    if lo > 0:
        return "**edge** (CI above 0)"
    if hi < 0:
        return "losing (CI below 0)"
    return "no edge yet (CI spans 0)"


def table(rows, cols):
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" if i == 0 else "--:" for i in range(len(cols))) + "|"]
    out += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    return "\n".join(out)


def stats_by_strategy(scored):
    g = collections.defaultdict(list)
    for r in scored:
        g[(r["rule"], int(r["H"]))].append(r)
    rows = []
    for (rule, H), rs in sorted(g.items()):
        f = [r for r in rs if r["filled"] == "1"]
        xs = [float(r["pnl"]) for r in f]
        if len(f) >= 15:
            lo, hi = boot(xs, [r["event"] for r in f])
            ci = f"{money(lo)} to {money(hi)}"
        else:
            lo, hi, ci = 0, 0, "—"
        rows.append(dict(name=f"`{rule}` {H}h", orders=len(rs), fills=len(f),
                         rate=f"{len(f) / len(rs):.0%}" if rs else "—",
                         per=money(mean(xs)) if xs else "—", ci=ci,
                         total=f"${sum(xs):+.2f}" if xs else "$0.00",
                         verdict=verdict(len(f), lo, hi), _total=sum(xs)))
    return rows


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    orders, scored = read(ORDERS), read(SCORED)
    today = [r for r in scored if r["scored_utc"][:10] == day]
    logged_today = [r for r in orders if r["logged_utc"][:10] == day and r["side"] != "none"]
    tf = [r for r in today if r["filled"] == "1"]
    day_pnl = sum(float(r["pnl"]) for r in tf)
    allf = [r for r in scored if r["filled"] == "1"]
    first = min((r["logged_utc"][:10] for r in orders), default=day)

    L = [f"# Paper trading report — {day}", "",
         f"Tracking since {first}. One contract per order, maker orders resting {6}h, "
         "filled only if a trade printed through the price; P&L after Kalshi maker fee. No real money.", "",
         "## Today", "",
         f"- Orders logged: **{len(logged_today)}** across "
         f"{len({(r['rule'], r['H'], r['event']) for r in logged_today})} rule/event pairs",
         f"- Orders settled and scored: **{len(today)}**, filled **{len(tf)}**",
         f"- Day P&L: **${day_pnl:+.2f}** ({money(day_pnl / len(tf)) if tf else '—'} per filled contract)",
         ""]

    if today:
        g = collections.defaultdict(list)
        for r in today:
            g[(r["rule"], int(r["H"]))].append(r)
        rows = []
        for (rule, H), rs in sorted(g.items()):
            f = [float(r["pnl"]) for r in rs if r["filled"] == "1"]
            rows.append((f"`{rule}` {H}h", len(rs), len(f), money(mean(f)) if f else "—", f"${sum(f):+.2f}"))
        L += ["### Settled today by strategy", "", table(rows, ["Strategy", "Orders", "Fills", "P&L / contract", "Total"]), ""]
        fills = sorted(tf, key=lambda r: (r["event"], r["ticker"], r["rule"]))
        rows = [(r["event"], r["ticker"].split("-")[-1], f"`{r['rule']}` {r['H']}h",
                 "buy YES" if r["side"] == "buy_yes" else "sell YES", f"{float(r['price']):.2f}",
                 r["result"].upper(), money(float(r["pnl"]))) for r in fills]
        L += ["<details><summary>Filled orders today</summary>", "",
              table(rows, ["Event", "Bucket", "Strategy", "Side", "Price", "Result", "P&L"]), "", "</details>", ""]

    cum = stats_by_strategy(scored)
    L += ["## Cumulative scoreboard", "",
          f"Verdict needs {MIN_FILLS}+ fills; CI is 95%, resampled by event.", "",
          table([(r["name"], r["orders"], r["fills"], r["rate"], r["per"], r["ci"], r["total"], r["verdict"]) for r in cum],
                ["Strategy", "Orders", "Fills", "Fill rate", "P&L / contract", "95% CI", "Total", "Verdict"])
          if cum else "_No settled orders yet._", ""]

    byday = collections.defaultdict(list)
    for r in allf:
        byday[r["scored_utc"][:10]].append(float(r["pnl"]))
    if byday:
        run, rows = 0.0, []
        for d in sorted(byday):
            run += sum(byday[d])
            rows.append((d, len(byday[d]), f"${sum(byday[d]):+.2f}", f"${run:+.2f}"))
        L += ["## Daily P&L (all strategies)", "", table(rows[-14:], ["Date", "Fills", "Day", "Cumulative"]), ""]

    os.makedirs(REPORTS, exist_ok=True)
    with open(os.path.join(REPORTS, f"{day}.md"), "w") as f:
        f.write("\n".join(L) + "\n")

    recent = sorted((x[:-3] for x in os.listdir(REPORTS) if x.endswith(".md")), reverse=True)[:14]
    R = ["# Kalshi weather paper trading", "",
         "Forward test of forecast-free rules on Kalshi daily-high temperature markets "
         "(rules in [strategies.py](strategies.py); backtest in [explore.py](explore.py)). No real money.", "",
         f"## Scoreboard (as of {day})", "",
         table([(r["name"], r["fills"], r["per"], r["ci"], r["total"], r["verdict"]) for r in cum],
               ["Strategy", "Fills", "P&L / contract", "95% CI", "Total", "Verdict"]) if cum else "_No settled orders yet._",
         "", "## Daily reports", ""] + [f"- [{d}](reports/{d}.md)" for d in recent]
    with open(os.path.join(HERE, "README.md"), "w") as f:
        f.write("\n".join(R) + "\n")
    print("wrote", os.path.join("paper", "reports", f"{day}.md"))


if __name__ == "__main__":
    main()
