"""Self-contained HTML dashboard (no JS, no external assets) for the paper trader.

Called from report.py; writes docs/index.html at the repo root so GitHub Pages can serve it
(Settings -> Pages -> Deploy from branch -> main /docs).
"""
import collections, html, math

GREEN, RED, GRID = "#16a34a", "#dc2626", "#2a3140"
PALETTE = ["#38bdf8", "#f59e0b", "#a78bfa", "#f472b6", "#2dd4bf", "#fb923c", "#84cc16", "#e879f9"]


def _cls(x):
    return "pos" if x > 0 else "neg" if x < 0 else "flat"


def _usd(x):
    return f"{'-' if x < 0 else '+'}${abs(x):,.2f}"


def _cents(x):
    return f"{x * 100:+.1f}¢"


def metrics(pnls_by_day):
    """pnls_by_day: {date: [pnl,...]} -> dict of headline stats."""
    days = sorted(pnls_by_day)
    flat = [p for d in days for p in pnls_by_day[d]]
    daily = [sum(pnls_by_day[d]) for d in days]
    wins, losses = [p for p in flat if p > 0], [p for p in flat if p < 0]
    eq, peak, mdd, run = [], 0.0, 0.0, 0.0
    for v in daily:
        run += v
        eq.append(run)
        peak = max(peak, run)
        mdd = max(mdd, peak - run)
    mu = sum(daily) / len(daily) if daily else 0
    sd = math.sqrt(sum((v - mu) ** 2 for v in daily) / (len(daily) - 1)) if len(daily) > 1 else 0
    return dict(
        n=len(flat), total=sum(flat), per=sum(flat) / len(flat) if flat else 0,
        win=len(wins) / len(flat) if flat else 0,
        pf=sum(wins) / -sum(losses) if losses else (float("inf") if wins else 0),
        avg_win=sum(wins) / len(wins) if wins else 0, avg_loss=sum(losses) / len(losses) if losses else 0,
        sharpe=(mu / sd * math.sqrt(365)) if sd else 0, mdd=mdd,
        best=max(daily, default=0), worst=min(daily, default=0),
        days=days, daily=daily, equity=eq, up_days=sum(1 for v in daily if v > 0),
    )


def equity_svg(series, w=900, h=300):
    """series: [(label, color, [(x_index, y)])] sharing an x axis of dates."""
    pad_l, pad_r, pad_t, pad_b = 54, 14, 14, 26
    pts = [y for _, _, s in series for _, y in s] + [0]
    lo, hi = min(pts), max(pts)
    if hi == lo:
        hi, lo = hi + 1, lo - 1
    nx = max((x for _, _, s in series for x, _ in s), default=0)
    X = lambda i: pad_l + (w - pad_l - pad_r) * (i / nx if nx else 0.5)
    Y = lambda v: pad_t + (h - pad_t - pad_b) * (1 - (v - lo) / (hi - lo))
    o = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="Cumulative P&L">']
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        o.append(f'<line x1="{pad_l}" x2="{w - pad_r}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{GRID}" stroke-width="1"/>'
                 f'<text x="{pad_l - 8}" y="{Y(v) + 4:.1f}" text-anchor="end" class="ax">${v:,.2f}</text>')
    o.append(f'<line x1="{pad_l}" x2="{w - pad_r}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" stroke="#6b7280" stroke-dasharray="4 4"/>')
    for i, (label, color, s) in enumerate(series):
        if not s:
            continue
        d = " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in s)
        if i == 0:  # headline series gets a gradient area
            last = s[-1][1]
            c = GREEN if last >= 0 else RED
            area = f"{X(s[0][0]):.1f},{Y(0):.1f} {d} {X(s[-1][0]):.1f},{Y(0):.1f}"
            o.append(f'<polygon points="{area}" fill="{c}" opacity="0.14"/>')
            o.append(f'<polyline points="{d}" fill="none" stroke="{c}" stroke-width="2.6" stroke-linejoin="round"/>')
            o.append(f'<circle cx="{X(s[-1][0]):.1f}" cy="{Y(last):.1f}" r="4.5" fill="{c}"/>')
        else:
            o.append(f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="1.5" opacity="0.85"/>')
    o.append("</svg>")
    return "".join(o)


def bars_svg(days, vals, w=900, h=180):
    if not vals:
        return ""
    pad_l, pad_r, pad_t, pad_b = 54, 14, 10, 22
    m = max(max(abs(v) for v in vals), 0.01)
    Y = lambda v: pad_t + (h - pad_t - pad_b) * (1 - (v + m) / (2 * m))
    bw = (w - pad_l - pad_r) / len(vals)
    o = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="Daily P&L">',
         f'<line x1="{pad_l}" x2="{w - pad_r}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" stroke="#6b7280"/>',
         f'<text x="{pad_l - 8}" y="{Y(m) + 4:.1f}" text-anchor="end" class="ax">${m:,.2f}</text>',
         f'<text x="{pad_l - 8}" y="{Y(-m) + 4:.1f}" text-anchor="end" class="ax">-${m:,.2f}</text>']
    for i, (d, v) in enumerate(zip(days, vals)):
        x, y0, y1 = pad_l + i * bw + bw * 0.12, Y(max(v, 0)), Y(min(v, 0))
        o.append(f'<rect x="{x:.1f}" y="{y0:.1f}" width="{bw * 0.76:.1f}" height="{max(y1 - y0, 1):.1f}" rx="2" '
                 f'fill="{GREEN if v >= 0 else RED}"><title>{d}: {_usd(v)}</title></rect>')
    o.append(f'<text x="{pad_l}" y="{h - 5}" class="ax">{days[0]}</text>'
             f'<text x="{w - pad_r}" y="{h - 5}" text-anchor="end" class="ax">{days[-1]}</text></svg>')
    return "".join(o)


def card(label, value, cls="", sub=""):
    return (f'<div class="card"><div class="lbl">{label}</div><div class="val {cls}">{value}</div>'
            f'<div class="sub">{sub}</div></div>')


def render(orders, scored, cum, day, min_fills):
    esc = html.escape
    filled = [r for r in scored if r["filled"] == "1"]
    byday = collections.defaultdict(list)
    for r in filled:
        byday[r["scored_utc"][:10]].append(float(r["pnl"]))
    M = metrics(byday)

    # equity series: total first, then each strategy
    days = M["days"]
    idx = {d: i for i, d in enumerate(days)}
    series = [("Total", GREEN, [(i, e) for i, e in enumerate(M["equity"])])]
    per = collections.defaultdict(lambda: collections.defaultdict(float))
    for r in filled:
        per[f"{r['rule']} {r['H']}h"][r["scored_utc"][:10]] += float(r["pnl"])
    for k, (name, dd) in enumerate(sorted(per.items())):
        run, s = 0.0, []
        for d in days:
            run += dd.get(d, 0.0)
            s.append((idx[d], run))
        series.append((name, PALETTE[k % len(PALETTE)], s))
    legend = "".join(f'<span><i style="background:{c}"></i>{esc(n)}</span>' for n, c, _ in series[1:])

    placed = [r for r in orders if r["side"] != "none"]
    open_n = len(placed) - len(scored) if len(placed) > len(scored) else 0
    pf = "∞" if M["pf"] == float("inf") else f"{M['pf']:.2f}"
    cards = "".join([
        card("Total P&L", _usd(M["total"]), _cls(M["total"]), f"{M['n']} filled contracts"),
        card("P&L / contract", _cents(M["per"]), _cls(M["per"]), "after maker fee"),
        card("Win rate", f"{M['win']:.0%}" if M["n"] else "—", "", f"avg win {_cents(M['avg_win'])} · avg loss {_cents(M['avg_loss'])}"),
        card("Profit factor", pf if M["n"] else "—", "pos" if M["pf"] > 1 else "neg" if M["n"] else "", "gross wins / gross losses"),
        card("Sharpe (ann.)", f"{M['sharpe']:.2f}" if len(days) > 1 else "—", _cls(M["sharpe"]), "daily P&L, √365"),
        card("Max drawdown", f"-${M['mdd']:,.2f}" if M["n"] else "—", "neg" if M["mdd"] else "", "peak to trough"),
        card("Best / worst day", f"{_usd(M['best'])} / {_usd(M['worst'])}" if days else "—", "",
             f"{M['up_days']} of {len(days)} days green"),
        card("Open orders", str(open_n), "", f"{len(placed)} logged · {len(scored)} settled"),
    ])

    rows = []
    for r in cum:
        v = r["verdict"].replace("**", "")
        vc = "pos" if v.startswith("edge") else "neg" if v.startswith("losing") else "flat"
        rows.append(f'<tr><td>{r["name"].replace("`", "")}</td><td>{r["orders"]}</td><td>{r["fills"]}</td>'
                    f'<td>{r["rate"]}</td><td class="{_cls(r["_total"])}">{r["per"]}</td><td>{r["ci"]}</td>'
                    f'<td class="{_cls(r["_total"])}">{r["total"]}</td><td><span class="pill {vc}">{esc(v)}</span></td></tr>')
    strat = ("<table><thead><tr><th>Strategy</th><th>Orders</th><th>Fills</th><th>Fill rate</th><th>P&amp;L / contract</th>"
             "<th>95% CI</th><th>Total</th><th>Verdict</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
             if rows else '<p class="muted">No settled orders yet — first results arrive after markets close.</p>')

    recent = sorted(filled, key=lambda r: r["scored_utc"], reverse=True)[:25]
    fr = "".join(
        f'<tr><td>{esc(r["scored_utc"][:16].replace("T", " "))}</td><td>{esc(r["ticker"])}</td>'
        f'<td>{esc(r["rule"])} {esc(r["H"])}h</td><td>{"buy YES" if r["side"] == "buy_yes" else "sell YES"}</td>'
        f'<td>{float(r["price"]):.2f}</td><td>{esc(r["result"].upper())}</td>'
        f'<td class="{_cls(float(r["pnl"]))}">{_cents(float(r["pnl"]))}</td></tr>' for r in recent)
    fills_tbl = (f'<table><thead><tr><th>Settled</th><th>Market</th><th>Strategy</th><th>Side</th><th>Price</th>'
                 f'<th>Result</th><th>P&amp;L</th></tr></thead><tbody>{fr}</tbody></table>' if fr else
                 '<p class="muted">No fills yet.</p>')

    charts = (f'<div class="legend"><span><i style="background:{GREEN}"></i>Total</span>{legend}</div>'
              + equity_svg(series) if days else '<p class="muted">Charts appear once the first orders settle.</p>')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kalshi Weather Paper Trading</title>
<style>
:root{{--bg:#0b0f17;--panel:#131a26;--line:#222b3b;--fg:#e6edf6;--mut:#8a97ab;--g:{GREEN};--r:{RED}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif}}
.wrap{{max-width:1040px;margin:0 auto;padding:28px 16px 60px}}
h1{{font-size:24px;margin:0}}h2{{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);margin:34px 0 12px}}
.top{{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:8px}}
.muted,.sub,.ax{{color:var(--mut)}}.sub{{font-size:12px}}.ax{{fill:var(--mut);font-size:11px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));gap:12px}}
.card,.panel{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px}}
.lbl{{font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em}}
.val{{font-size:26px;font-weight:700;margin:4px 0 2px;font-variant-numeric:tabular-nums}}
.pos{{color:#4ade80}}.neg{{color:#f87171}}.flat{{color:var(--mut)}}
.chart{{width:100%;height:auto;display:block}}
.legend{{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--mut);margin-bottom:6px}}
.legend i{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px}}
table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}}
th,td{{padding:9px 10px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}}
th:first-child,td:first-child{{text-align:left}}th{{font-size:12px;color:var(--mut);font-weight:600}}
tbody tr:hover{{background:#182032}}.scroll{{overflow-x:auto}}
.pill{{padding:2px 9px;border-radius:99px;font-size:12px;background:#1f2937}}
.pill.pos{{background:#14532d;color:#86efac}}.pill.neg{{background:#7f1d1d;color:#fca5a5}}
</style></head><body><div class="wrap">
<div class="top"><div><h1>Kalshi Weather · Paper Trading</h1>
<div class="muted">Forecast-free rules on daily-high temperature markets · simulated maker orders · no real money</div></div>
<div class="muted">As of {esc(day)} (UTC)</div></div>
<h2>Performance</h2><div class="grid">{cards}</div>
<h2>Cumulative P&amp;L</h2><div class="panel">{charts}</div>
<h2>Daily P&amp;L</h2><div class="panel">{bars_svg(days, M["daily"]) or '<p class="muted">No settled days yet.</p>'}</div>
<h2>Strategies</h2><div class="panel scroll">{strat}<p class="sub">Verdict needs {min_fills}+ fills; CI is 95%, resampled by event.</p></div>
<h2>Recent fills</h2><div class="panel scroll">{fills_tbl}</div>
</div></body></html>
"""
