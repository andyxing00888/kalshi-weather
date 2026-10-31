"""Momentum or overreaction? Does the 24h->6h price move predict the outcome beyond the 6h price?

Uses markets cached by calib.py (data/calib.csv, data/calib_nonsports.csv). For each market with tight
quotes (spread <= 5c) at both times: d = mid(6h) - mid(24h), resid = outcome - mid(6h).
  slope of resid on d > 0: underreaction (follow moves);  < 0: overreaction (fade moves)
Rules at 6h before close, taker at the quote: follow (buy YES if d > X, sell if d < -X) and fade.
Usage: python3 drift.py [X ...]   (default 0.05 0.10 0.20)
"""
import csv, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper"))
from common import boot, mean, fee  # noqa: E402
import calib  # noqa: E402

FILES = {"sports": "calib.csv", "non-sports": "calib_nonsports.csv"}
T1, T2, MAX_SPREAD = 24, 6, 0.05


def load(fname):
    out = []
    for r in csv.DictReader(open(os.path.join(calib.DATA, fname))):
        cs = json.load(open(os.path.join(calib.CACHE, r["ticker"] + ".json")))
        close = int(r["close"])
        q = []
        for H in (T1, T2):
            t = close - H * 3600
            x = calib.quote(cs, t - t % 3600)
            if not x or not (0 < x[0] < x[1] < 1) or x[1] - x[0] > MAX_SPREAD:
                break
            q.append(x)
        if len(q) == 2 and int(r["open"]) < close - T1 * 3600:
            (b1, a1), (b2, a2) = q
            out.append(dict(event=r["event"], d=(b2 + a2) / 2 - (b1 + a1) / 2, m=(b2 + a2) / 2,
                            b=b2, a=a2, y=1.0 if r["result"] == "yes" else 0.0))
    return out


def ci(xs):
    lo, hi = boot([x for _, x in xs], [e for e, _ in xs], n=500)
    return f"n={len(xs):4d} ev={len({e for e, _ in xs}):4d} {mean([x for _, x in xs]) * 100:+5.1f}¢ [{lo * 100:+5.1f},{hi * 100:+5.1f}]"


def main():
    xs = [float(a) for a in sys.argv[1:]] or [0.05, 0.10, 0.20]
    for name, f in FILES.items():
        if not os.path.exists(os.path.join(calib.DATA, f)):
            continue
        rs = load(f)
        moved = [r for r in rs if abs(r["d"]) > 1e-9]
        sxx = sum(r["d"] ** 2 for r in moved)
        slope = sum(r["d"] * (r["y"] - r["m"]) for r in moved) / sxx if sxx else 0
        print(f"\n=== {name}: {len(rs)} markets with tight quotes at {T1}h and {T2}h, {len(moved)} moved;"
              f" slope of (outcome - mid{T2}) on move = {slope:+.3f}")
        for X in xs:
            follow, fade = [], []
            for r in rs:
                if r["d"] > X:
                    follow.append((r["event"], r["y"] - r["a"] - fee(r["a"])))
                    fade.append((r["event"], r["b"] - r["y"] - fee(1 - r["b"])))
                elif r["d"] < -X:
                    follow.append((r["event"], r["b"] - r["y"] - fee(1 - r["b"])))
                    fade.append((r["event"], r["y"] - r["a"] - fee(r["a"])))
            if follow:
                print(f"  |move|>{X:.2f}  follow {ci(follow)}   fade {ci(fade)}")


if __name__ == "__main__":
    main()
