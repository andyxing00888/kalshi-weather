"""Compare a forecast-based probability model to Kalshi prices on settled markets.

Usage: python3 analyze.py [hours_before_close]   (default 12)
Needs data/markets.csv, data/candles.csv, data/forecasts.csv.
Model: actual high ~ Normal(fc_high_f, sigma), sigma = expanding-window RMSE of (value - fc) per series (walk-forward),
integer-rounded settlement so bucket probs use +-0.5 continuity correction.
Reports Brier score of model vs market price at the chosen horizon.
"""
import csv, math, os, random, sys, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper"))
from common import fee  # noqa: E402,F401  (re-exported for the older backtests)

EDGE = float(os.environ.get("EDGE", 0.05))
DIST = os.environ.get("DIST", "normal")      # normal | emp (kernel-smoothed residuals)
WEIGHT = os.environ.get("WEIGHT", "equal")  # equal | inv (inverse recent MSE per model)
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def rd(name):
    with open(os.path.join(DATA, name)) as f:
        return list(csv.DictReader(f))


def cdf(x, mu, s):
    return 0.5 * (1 + math.erf((x - mu) / (s * math.sqrt(2))))


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None  # empty, or non-numeric expiration_value like "70° to 71°"


def model_p(m, mu, s, res=None):
    if DIST == "emp" and res:
        cdf_ = lambda x, mu_, s_: sum(cdf(x, mu_ + e, 0.8) for e in res) / len(res)
    else:
        cdf_ = cdf
    return _model_p(m, mu, s, cdf_)


def _model_p(m, mu, s, cdf):
    st, lo, hi = m["strike_type"], fnum(m["floor"]), fnum(m["cap"])
    if st == "between":
        return cdf(hi + 0.5, mu, s) - cdf(lo - 0.5, mu, s)
    if st == "greater":
        return 1 - cdf(lo + 0.5, mu, s)
    if st == "less":
        return cdf(hi - 0.5, mu, s)
    return None


def main():
    hrs = float(sys.argv[1]) if len(sys.argv) > 1 else 12
    mode = sys.argv[2] if len(sys.argv) > 2 else "raw"  # raw | bc | ens
    markets = rd("markets.csv")
    fc = {(r["series"], r["date"]): float(r["fc_high_f"]) for r in rd("forecasts.csv")}
    candles = collections.defaultdict(list)
    for c in rd("candles.csv"):
        candles[c["ticker"]].append(c)

    # event date = local date of the settlement day; parse from event ticker suffix (e.g. 25OCT30)
    def edate(ev):
        s = ev.split("-")[-1]
        mon = dict(JAN=1, FEB=2, MAR=3, APR=4, MAY=5, JUN=6, JUL=7, AUG=8, SEP=9,
                   OCT=10, NOV=11, DEC=12)[s[2:5]]
        return f"20{s[:2]}-{mon:02d}-{s[5:7]}"

    # walk-forward: sigma for a day uses only errors from strictly earlier days
    errs = collections.defaultdict(dict)
    for m in markets:
        v = fnum(m["value"])
        d = edate(m["event"])
        if v is not None and (m["series"], d) in fc:
            errs[m["series"]][d] = v - fc[(m["series"], d)]

    # walk-forward (mu, sigma) per (series, date); every input is from strictly earlier days
    truth = {(s_, d): e + fc[(s_, d)] for s_, dd in errs.items() for d, e in dd.items()}
    MODELS = ["gfs_seamless", "ecmwf_ifs025", "icon_seamless", "gem_seamless", "ukmo_seamless"]
    multi = {(r["series"], r["date"]): {k[3:]: float(v) for k, v in r.items()
                                        if k.startswith("fc_") and v != ""}
             for r in rd("forecasts_multi.csv")} if mode == "ens" else {}
    BIAS_WIN, SIG_WIN = 30, 40

    def mean(xs):
        return sum(xs) / len(xs)

    pred = {}
    for s_ in errs:
        dates = sorted(d for (ss, d) in fc if ss == s_)
        resid = []  # walk-forward residuals of this mode
        for d in dates:
            prior = [x for x in dates if x < d and (s_, x) in truth][-BIAS_WIN:]
            if mode == "raw":
                mu = fc[(s_, d)]
            elif mode == "bc":
                if len(prior) < 10:
                    continue
                mu = fc[(s_, d)] + mean([errs[s_][x] for x in prior])
            else:  # ens: mean of per-model bias-corrected forecasts
                cur = multi.get((s_, d), {})
                parts, ws = [], []
                for m in MODELS:
                    hist = [truth[(s_, x)] - multi[(s_, x)][m] for x in prior
                            if m in multi.get((s_, x), {})]
                    if m in cur and len(hist) >= 10:
                        b = mean(hist)
                        parts.append(cur[m] + b)
                        ws.append(1 / max(mean([(h - b) ** 2 for h in hist]), 0.25)
                                  if WEIGHT == "inv" else 1.0)
                if len(parts) < 3:
                    continue
                mu = sum(w * p_ for w, p_ in zip(ws, parts)) / sum(ws)
            r = resid[-SIG_WIN:]  # residuals of earlier days only
            sg = math.sqrt(sum(e * e for e in r) / len(r)) if len(r) >= 20 else None
            pred[(s_, d)] = [mu, sg, r]
            if (s_, d) in truth:
                resid.append(truth[(s_, d)] - mu)

    def sigma_before(s, d):
        return pred.get((s, d), [None, None])[1]

    from datetime import datetime
    recs = []  # (series, p_model, p_mkt, y, pnl_per_contract)
    for m in markets:
        d = edate(m["event"])
        if (m["series"], d) not in pred:
            continue
        sg = sigma_before(m["series"], d)
        if sg is None:
            continue
        p = model_p(m, pred[(m["series"], d)][0], sg, pred[(m["series"], d)][2])
        if p is None:
            continue
        close = datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).timestamp()
        cs = [c for c in candles[m["ticker"]] if float(c["end_ts"]) <= close - hrs * 3600
              and c["price_close"] not in ("", None)]
        if not cs:
            continue
        c = max(cs, key=lambda c: float(c["end_ts"]))
        q = float(c["price_close"])
        y = 1.0 if m["result"] == "yes" else 0.0
        pnl = None
        ask, bid = fnum(c["ask_close"]), fnum(c["bid_close"])
        if ask and p - ask > EDGE:
            pnl = y - ask - fee(ask)
        elif bid and bid - p > EDGE:
            pnl = (1 - y) - (1 - bid) - fee(1 - bid)
        recs.append((m["series"], p, q, y, pnl, m["event"]))

    def boot(xs, n=2000, keys=None):
        # cluster bootstrap: resample whole events (markets in an event share an outcome)
        rng = random.Random(0)
        g = collections.defaultdict(list)
        for k, x in zip(keys or range(len(xs)), xs):
            g[k].append(x)
        gs = list(g.values())
        ms = []
        for _ in range(n):
            pick = [x for grp in rng.choices(gs, k=len(gs)) for x in grp]
            ms.append(sum(pick) / len(pick))
        ms.sort()
        return ms[int(.025 * n)], ms[int(.975 * n)]

    print(f"n={len(recs)} markets, horizon {hrs:g}h, mode {mode}")
    bm = [(p - y) ** 2 for _, p, _, y, _, _ in recs]
    bk = [(q - y) ** 2 for _, _, q, y, _, _ in recs]
    diff = [a - b for a, b in zip(bm, bk)]
    lo, hi = boot(diff, keys=[r[5] for r in recs])
    print(f"Brier model {sum(bm)/len(bm):.4f} market {sum(bk)/len(bk):.4f} "
          f"diff {sum(diff)/len(diff):+.4f} [{lo:+.4f},{hi:+.4f}] (neg = model better)")
    tr = [r[4] for r in recs if r[4] is not None]
    if tr:
        lo, hi = boot(tr, keys=[r[5] for r in recs if r[4] is not None])
        print(f"trades (edge>{EDGE}, cross spread, after fees): n={len(tr)} "
              f"mean pnl/contract {sum(tr)/len(tr):+.4f} [{lo:+.4f},{hi:+.4f}]")
    print("blend (1-w)*market + w*model Brier:",
          " ".join(f"w={w:.1f}:{sum(((1-w)*r[2]+w*r[1]-r[3])**2 for r in recs)/len(recs):.4f}"
                   for w in (0, .1, .2, .3, .5, 1)))
    by = collections.defaultdict(list)
    for r in recs:
        by[r[0]].append(r)
    print("series      n  brier_model brier_mkt")
    for s_, rs in sorted(by.items()):
        print(f"{s_:11s}{len(rs):4d} {sum((r[1]-r[3])**2 for r in rs)/len(rs):9.4f} "
              f"{sum((r[2]-r[3])**2 for r in rs)/len(rs):9.4f}")


if __name__ == "__main__":
    main()
