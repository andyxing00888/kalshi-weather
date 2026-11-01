# Kalshi paper trading

Forward test of Kalshi strategies: forecast-free rules on weather, econ and a diversified non-sports basket (rules in [strategies.py](paper/strategies.py)), plus the experiments below.

## Summary (as of 2026-11-01)

| Metric | Value |
|---|--:|
| 🟢 Total P&L | **$+2.16** over 12 fills |
| 🟢 P&L / contract | +18.0¢ |
| Win rate | 100% |
| Profit factor | ∞ |
| Max drawdown | -$0.00 |
| Sharpe (ann.) | — |
| 🟢 Today | $+2.16 (12 fills) |

Full dashboard: https://functionalleaf.github.io/kalshi-weather/

## Other experiments

| Experiment | Data | Status |
|---|--:|--:|
| Liquidity rewards (`lip.py`), 300/side on watchlist | 21 runs / ~25h | rewards $715.46, fills $+0.00 (0 settled, 12856.2 open) → **net $+715.46** |
| S&P/Nasdaq cross-series arb (`consistency.py`) | 20 runs | 0 arbs after fees, best edge -2.0¢ |
| Kalshi vs Polymarket sports (`xvenue.py`) | 20 runs | 1366 team quotes, 0 buy-Kalshi arbs after fees |

## Scoreboard

| Strategy | Fills | P&L / contract | 95% CI | Total | Verdict |
|---|--:|--:|--:|--:|--:|
| `fav_longshot` 24h | 7 | +21.1¢ | — | $+1.48 | collecting (7/100) |
| `fav_longshot` 30h | 0 | — | — | $0.00 | collecting (0/100) |
| `overround` 24h | 1 | +23.0¢ | — | $+0.23 | collecting (1/100) |
| `overround` 30h | 1 | +28.0¢ | — | $+0.28 | collecting (1/100) |
| `sell_longshot` 12h | 0 | — | — | $0.00 | collecting (0/100) |
| `sell_longshot_div` 6h | 3 | +5.7¢ | — | $+0.17 | collecting (3/100) |
| `tails` 24h | 0 | — | — | $0.00 | collecting (0/100) |
| `tails` 30h | 0 | — | — | $0.00 | collecting (0/100) |

## Daily reports

- [2026-11-01](paper/reports/2026-11-01.md)
- [2026-10-31](paper/reports/2026-10-31.md)
