# Kalshi paper trading

Forward test of Kalshi strategies: forecast-free rules on weather, econ and a diversified non-sports basket (rules in [strategies.py](paper/strategies.py)), plus the experiments below.

## Summary (as of 2026-11-03)

| Metric | Value |
|---|--:|
| 🔴 Total P&L | **$-6.10** over 139 fills |
| 🔴 P&L / contract | -4.4¢ |
| Win rate | 71% |
| Profit factor | 0.76 |
| Max drawdown | -$8.26 |
| Sharpe (ann.) | -9.15 |
| 🔴 Today | $-1.93 (83 fills) |

Full dashboard: https://functionalleaf.github.io/kalshi-weather/

## Other experiments

| Experiment | Data | Status |
|---|--:|--:|
| Liquidity rewards (`lip.py`), 300/side on watchlist | 57 runs / ~27h | rewards $1,544.84, fills $-2,224.12 (20797.2 settled, 17576.4 open) → **net $-679.28** |
| S&P/Nasdaq cross-series arb (`consistency.py`) | 49 runs | 0 arbs after fees, best edge -1.0¢ |
| Kalshi vs Polymarket sports (`xvenue.py`) | 56 runs | 3170 team quotes, 0 buy-Kalshi arbs after fees |

## Scoreboard

| Strategy | Fills | P&L / contract | 95% CI | Total | Verdict |
|---|--:|--:|--:|--:|--:|
| `fade_move` 18h | 7 | +13.1¢ | — | $+0.92 | collecting (7/100) |
| `fade_move` 24h | 2 | -9.0¢ | — | $-0.18 | collecting (2/100) |
| `fade_move` 30h | 2 | -19.0¢ | — | $-0.38 | collecting (2/100) |
| `fav_longshot` 18h | 22 | -8.9¢ | -31.8¢ to +12.2¢ | $-1.95 | collecting (22/100) |
| `fav_longshot` 24h | 24 | +3.6¢ | -21.4¢ to +26.3¢ | $+0.87 | collecting (24/100) |
| `fav_longshot` 30h | 13 | -8.0¢ | — | $-1.04 | collecting (13/100) |
| `follow_move` 18h | 7 | -14.0¢ | — | $-0.98 | collecting (7/100) |
| `follow_move` 24h | 3 | -9.3¢ | — | $-0.28 | collecting (3/100) |
| `follow_move` 30h | 1 | -16.0¢ | — | $-0.16 | collecting (1/100) |
| `overround` 24h | 2 | -35.0¢ | — | $-0.70 | collecting (2/100) |
| `overround` 30h | 2 | +28.5¢ | — | $+0.57 | collecting (2/100) |
| `rv_updown_3c` 6h | 2 | -79.0¢ | — | $-1.58 | collecting (2/100) |
| `rv_updown_6c` 6h | 2 | -76.0¢ | — | $-1.52 | collecting (2/100) |
| `sell_longshot` 6h | 13 | +2.4¢ | — | $+0.31 | collecting (13/100) |
| `sell_longshot` 12h | 1 | +9.0¢ | — | $+0.09 | collecting (1/100) |
| `sell_longshot_div` 6h | 16 | +6.9¢ | +6.0¢ to +7.8¢ | $+1.11 | collecting (16/100) |
| `sell_longshot_div` 24h | 11 | +1.5¢ | — | $+0.16 | collecting (11/100) |
| `tails` 18h | 5 | -19.8¢ | — | $-0.99 | collecting (5/100) |
| `tails` 24h | 3 | -17.3¢ | — | $-0.52 | collecting (3/100) |
| `tails` 30h | 1 | +15.0¢ | — | $+0.15 | collecting (1/100) |

## Daily reports

- [2026-11-03](paper/reports/2026-11-03.md)
- [2026-11-02](paper/reports/2026-11-02.md)
- [2026-11-01](paper/reports/2026-11-01.md)
- [2026-10-31](paper/reports/2026-10-31.md)
