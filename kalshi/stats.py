"""Metrics shared by every backtest and the paper report."""
import collections, math, random


def mean(xs):
    return sum(xs) / len(xs)


def brier(ps, ys):
    """Mean squared error of probabilities ps against 0/1 outcomes ys."""
    return mean([(p - y) ** 2 for p, y in zip(ps, ys)])


def cdf(x, mu, s):
    """Normal CDF."""
    return 0.5 * (1 + math.erf((x - mu) / (s * math.sqrt(2))))


def boot(xs, keys=None, n=1000):
    """95% CI of the mean, resampling whole events (markets in an event share an outcome).
    keys[i] is the event of xs[i]; without it every observation is its own cluster."""
    rng = random.Random(0)
    g = collections.defaultdict(list)
    for k, x in zip(keys if keys is not None else range(len(xs)), xs):
        g[k].append(x)
    gs, ms = list(g.values()), []
    for _ in range(n):
        pick = [x for grp in rng.choices(gs, k=len(gs)) for x in grp]
        ms.append(sum(pick) / len(pick))
    ms.sort()
    return ms[int(.025 * n)], ms[int(.975 * n)]
