# Kalshi paper trading

Forward test of forecast-free rules on Kalshi daily-high temperature markets (rules in [strategies.py](paper/strategies.py); backtest in [explore.py](paper/explore.py)). 

## Summary (as of 2026-10-31)

_No filled contracts yet._

Full dashboard: https://functionalleaf.github.io/kalshi-weather/

## Other experiments

| Experiment | Data | Status |
|---|--:|--:|
| Liquidity rewards (`lip.py`), 300/side on watchlist | 3 runs / ~0h | rewards $7.39, fills $+0.00 (0 settled, 457.5 open) → **net $+7.39** |
| S&P/Nasdaq cross-series arb (`consistency.py`) | 2 runs | 0 arbs after fees, best edge -10.0¢ |
| Kalshi vs Polymarket sports (`xvenue.py`) | 2 runs | 160 team quotes, 0 buy-Kalshi arbs after fees |

## Scoreboard

_No settled orders yet._

## Daily reports

- [2026-10-31](paper/reports/2026-10-31.md)
