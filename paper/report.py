"""Daily paper-trading report.

  python3 -m paper.report [YYYY-MM-DD]   (default: today UTC)
Writes paper/reports/<date>.md (that day's settlements + cumulative stats) and README.md
(cumulative scoreboard, links to recent reports).
"""
import collections, os, sys
from datetime import datetime, timezone

from kalshi.fees import fee
from kalshi.paths import ROOT, PAPER, PAPER_DATA
from kalshi.stats import boot, mean
from kalshi.store import read
from paper import dashboard
from paper.trader import ORDERS, SCORED

REPORTS = os.path.join(PAPER, "reports")
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


def summary_lines(byday, today, tf, day_pnl):
    M = dashboard.metrics(byday)
    if not M["n"]:
        return ["_No filled contracts yet._"]
    pf = "∞" if M["pf"] == float("inf") else f"{M['pf']:.2f}"
    icon = lambda x: "🟢" if x > 0 else "🔴" if x < 0 else "⚪"
    return ["| Metric | Value |", "|---|--:|",
            f"| {icon(M['total'])} Total P&L | **${M['total']:+.2f}** over {M['n']} fills |",
            f"| {icon(M['per'])} P&L / contract | {money(M['per'])} |",
            f"| Win rate | {M['win']:.0%} |",
            f"| Profit factor | {pf} |",
            f"| Max drawdown | -${M['mdd']:.2f} |",
            f"| Sharpe (ann.) | {M['sharpe']:.2f} |" if len(M["days"]) > 1 else "| Sharpe (ann.) | — |",
            f"| {icon(day_pnl)} Today | ${day_pnl:+.2f} ({len(tf)} fills) |"]


def experiment_lines():
    """One-line status of the non-rule experiments that log on their own."""
    import lip
    rows = []
    try:
        L = lip.report(quiet=True)
        if L:
            rows.append(("Liquidity rewards (`lip.py`), 300/side on watchlist", f"{L['runs']} runs / ~{L['hours']:.0f}h",
                         f"rewards ${L['reward']:,.2f}, fills ${L['fill_pnl']:+,.2f} "
                         f"({L['settled']:g} settled, {L['open']:g} open) → **net ${L['net']:+,.2f}**"))
    except Exception as e:  # network or file trouble must not break the report
        rows.append(("Liquidity rewards (`lip.py`)", "—", f"error: {e}"))
    c = read(os.path.join(PAPER_DATA, "consistency.csv"))
    if c:
        arbs = [r for r in c if r["arb"] == "1"]
        best = max(float(r["edge"]) for r in c)
        rows.append(("S&P/Nasdaq cross-series arb (`consistency.py`)", f"{len({r['utc'] for r in c})} runs",
                     f"{len(arbs)} arbs after fees, best edge {best * 100:+.1f}¢"))
    x = read(os.path.join(PAPER_DATA, "xvenue.csv"))
    if x:
        f = lambda v: float(v) if v not in ("", None) else None
        n = 0
        for r in x:
            ka, pb = f(r["k_ask"]), f(r["p_bid"])
            if ka and pb and 0 < ka < 1 and 0 < pb < 1:
                o = 1 - pb
                n += 1 - ka - o - fee(ka) - 0.05 * o * (1 - o) > 0  # Polymarket sports taker fee
        rows.append(("Kalshi vs Polymarket sports (`xvenue.py`)", f"{len({r['utc'] for r in x})} runs",
                     f"{len(x)} team quotes, {n} buy-Kalshi arbs after fees"))
    return [table(rows, ["Experiment", "Data", "Status"])] if rows else []


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
    R = ["# Kalshi paper trading", "",
         "Forward test of Kalshi strategies: forecast-free rules on weather, econ and a diversified non-sports "
         "basket (rules in [strategies.py](paper/strategies.py)), plus the experiments below.", "",
         f"## Summary (as of {day})", "",
         *summary_lines(byday, today, tf, day_pnl), "",
         "Full dashboard: https://functionalleaf.github.io/kalshi-weather/", "",
         "## Other experiments", "", *experiment_lines(), "",
         "## Scoreboard", "",
         table([(r["name"], r["fills"], r["per"], r["ci"], r["total"], r["verdict"]) for r in cum],
               ["Strategy", "Fills", "P&L / contract", "95% CI", "Total", "Verdict"]) if cum else "_No settled orders yet._",
         "", "## Daily reports", ""] + [f"- [{d}](paper/reports/{d}.md)" for d in recent]
    with open(os.path.join(ROOT, "README.md"), "w") as f:
        f.write("\n".join(R) + "\n")
    docs = os.path.join(ROOT, "docs")
    os.makedirs(docs, exist_ok=True)
    with open(os.path.join(docs, "index.html"), "w") as f:
        f.write(dashboard.render(orders, scored, cum, day, MIN_FILLS))
    print("wrote", os.path.join("paper", "reports", f"{day}.md"), "and docs/index.html")


if __name__ == "__main__":
    main()
