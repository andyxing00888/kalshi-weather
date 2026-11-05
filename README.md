# Kalshi paper trading

Forward test of Kalshi strategies: forecast-free rules on weather, econ and a diversified non-sports basket (rules in [strategies.py](paper/strategies.py)), plus the experiments below.

## Summary (as of 2026-11-05)

| Metric | Value |
|---|--:|
| 🔴 Total P&L | **$-6.87** over 300 fills |
| 🔴 P&L / contract | -2.3¢ |
| Win rate | 74% |
| Profit factor | 0.86 |
| Max drawdown | -$9.03 |
| Sharpe (ann.) | -8.37 |
| 🔴 Today | $-0.54 (96 fills) |

Full dashboard: https://functionalleaf.github.io/kalshi-weather/

## Other experiments

| Experiment | Data | Status |
|---|--:|--:|
| Liquidity rewards (`lip.py`), 300/side on watchlist | 82 runs / ~29h | rewards $2,978.00, fills $-4,360.83 (28634.7 settled, 35889.3 open) → **net $-1,382.83** |
| S&P/Nasdaq cross-series arb (`consistency.py`) | 67 runs | 0 arbs after fees, best edge -1.0¢ |
| Kalshi vs Polymarket sports (`xvenue.py`) | 81 runs | 4474 team quotes, 0 buy-Kalshi arbs after fees |

## Scoreboard

| Strategy | Fills | P&L / contract | 95% CI | Total | Verdict |
|---|--:|--:|--:|--:|--:|
| `fade_move` 18h | 7 | +13.1¢ | — | $+0.92 | collecting (7/100) |
| `fade_move` 24h | 7 | -17.3¢ | — | $-1.21 | collecting (7/100) |
| `fade_move` 30h | 7 | -11.6¢ | — | $-0.81 | collecting (7/100) |
| `fav_longshot` 18h | 42 | -5.6¢ | -20.8¢ to +9.2¢ | $-2.37 | collecting (42/100) |
| `fav_longshot` 24h | 49 | +5.8¢ | -8.7¢ to +19.7¢ | $+2.86 | collecting (49/100) |
| `fav_longshot` 30h | 40 | -10.0¢ | -24.4¢ to +4.7¢ | $-3.99 | collecting (40/100) |
| `follow_move` 18h | 7 | -14.0¢ | — | $-0.98 | collecting (7/100) |
| `follow_move` 24h | 8 | +7.9¢ | — | $+0.63 | collecting (8/100) |
| `follow_move` 30h | 3 | -2.3¢ | — | $-0.07 | collecting (3/100) |
| `overround` 18h | 3 | +8.3¢ | — | $+0.25 | collecting (3/100) |
| `overround` 24h | 3 | -21.3¢ | — | $-0.64 | collecting (3/100) |
| `overround` 30h | 2 | +28.5¢ | — | $+0.57 | collecting (2/100) |
| `rv_updown_3c` 6h | 4 | -28.0¢ | — | $-1.12 | collecting (4/100) |
| `rv_updown_6c` 6h | 3 | -37.7¢ | — | $-1.13 | collecting (3/100) |
| `sell_longshot` 6h | 22 | +1.0¢ | -7.8¢ to +11.6¢ | $+0.22 | collecting (22/100) |
| `sell_longshot` 12h | 2 | +7.5¢ | — | $+0.15 | collecting (2/100) |
| `sell_longshot_div` 6h | 46 | +6.4¢ | +4.7¢ to +7.5¢ | $+2.93 | collecting (46/100) |
| `sell_longshot_div` 24h | 29 | -8.1¢ | -30.8¢ to +10.2¢ | $-2.35 | collecting (29/100) |
| `tails` 18h | 7 | -11.9¢ | — | $-0.83 | collecting (7/100) |
| `tails` 24h | 6 | -5.3¢ | — | $-0.32 | collecting (6/100) |
| `tails` 30h | 3 | +14.0¢ | — | $+0.42 | collecting (3/100) |

## Daily reports

- [2026-11-05](paper/reports/2026-11-05.md)
- [2026-11-04](paper/reports/2026-11-04.md)
- [2026-11-03](paper/reports/2026-11-03.md)
- [2026-11-02](paper/reports/2026-11-02.md)
- [2026-11-01](paper/reports/2026-11-01.md)
- [2026-10-31](paper/reports/2026-10-31.md)
