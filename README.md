# Kalshi paper trading

Forward test of Kalshi strategies: forecast-free rules on weather, econ and a diversified non-sports basket (rules in [strategies.py](paper/strategies.py)), plus the experiments below.

## Summary (as of 2026-11-02)

| Metric | Value |
|---|--:|
| 🔴 Total P&L | **$-4.17** over 56 fills |
| 🔴 P&L / contract | -7.4¢ |
| Win rate | 66% |
| Profit factor | 0.66 |
| Max drawdown | -$6.33 |
| Sharpe (ann.) | -6.64 |
| 🔴 Today | $-6.33 (44 fills) |

Full dashboard: https://functionalleaf.github.io/kalshi-weather/

## Other experiments

| Experiment | Data | Status |
|---|--:|--:|
| Liquidity rewards (`lip.py`), 300/side on watchlist | 42 runs / ~27h | rewards $1,154.50, fills $-208.76 (6137.43 settled, 26139.3 open) → **net $+945.74** |
| S&P/Nasdaq cross-series arb (`consistency.py`) | 41 runs | 0 arbs after fees, best edge -1.0¢ |
| Kalshi vs Polymarket sports (`xvenue.py`) | 41 runs | 2442 team quotes, 0 buy-Kalshi arbs after fees |

## Scoreboard

| Strategy | Fills | P&L / contract | 95% CI | Total | Verdict |
|---|--:|--:|--:|--:|--:|
| `fade_move` 18h | 3 | +42.3¢ | — | $+1.27 | collecting (3/100) |
| `fade_move` 24h | 1 | -60.0¢ | — | $-0.60 | collecting (1/100) |
| `fade_move` 30h | 1 | -53.0¢ | — | $-0.53 | collecting (1/100) |
| `fav_longshot` 18h | 7 | -25.6¢ | — | $-1.79 | collecting (7/100) |
| `fav_longshot` 24h | 17 | +9.6¢ | -16.9¢ to +29.6¢ | $+1.63 | collecting (17/100) |
| `fav_longshot` 30h | 5 | +4.2¢ | — | $+0.21 | collecting (5/100) |
| `follow_move` 18h | 3 | -43.3¢ | — | $-1.30 | collecting (3/100) |
| `follow_move` 24h | 2 | +7.5¢ | — | $+0.15 | collecting (2/100) |
| `follow_move` 30h | 0 | — | — | $0.00 | collecting (0/100) |
| `overround` 24h | 2 | -35.0¢ | — | $-0.70 | collecting (2/100) |
| `overround` 30h | 1 | +28.0¢ | — | $+0.28 | collecting (1/100) |
| `sell_longshot` 6h | 1 | +3.0¢ | — | $+0.03 | collecting (1/100) |
| `sell_longshot` 12h | 1 | +9.0¢ | — | $+0.09 | collecting (1/100) |
| `sell_longshot_div` 6h | 5 | +6.8¢ | — | $+0.34 | collecting (5/100) |
| `sell_longshot_div` 24h | 4 | -16.2¢ | — | $-0.65 | collecting (4/100) |
| `tails` 18h | 2 | -83.5¢ | — | $-1.67 | collecting (2/100) |
| `tails` 24h | 1 | -93.0¢ | — | $-0.93 | collecting (1/100) |
| `tails` 30h | 0 | — | — | $0.00 | collecting (0/100) |

## Daily reports

- [2026-11-02](paper/reports/2026-11-02.md)
- [2026-11-01](paper/reports/2026-11-01.md)
- [2026-10-31](paper/reports/2026-10-31.md)
