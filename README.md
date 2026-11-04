# Kalshi paper trading

Forward test of Kalshi strategies: forecast-free rules on weather, econ and a diversified non-sports basket (rules in [strategies.py](paper/strategies.py)), plus the experiments below.

## Summary (as of 2026-11-04)

| Metric | Value |
|---|--:|
| 🔴 Total P&L | **$-6.33** over 204 fills |
| 🔴 P&L / contract | -3.1¢ |
| Win rate | 73% |
| Profit factor | 0.81 |
| Max drawdown | -$8.49 |
| Sharpe (ann.) | -8.44 |
| 🔴 Today | $-0.23 (65 fills) |

Full dashboard: https://functionalleaf.github.io/kalshi-weather/

## Other experiments

| Experiment | Data | Status |
|---|--:|--:|
| Liquidity rewards (`lip.py`), 300/side on watchlist | 77 runs / ~28h | rewards $2,031.13, fills $-2,224.12 (20797.2 settled, 30927.4 open) → **net $-192.99** |
| S&P/Nasdaq cross-series arb (`consistency.py`) | 62 runs | 0 arbs after fees, best edge -1.0¢ |
| Kalshi vs Polymarket sports (`xvenue.py`) | 76 runs | 4204 team quotes, 0 buy-Kalshi arbs after fees |

## Scoreboard

| Strategy | Fills | P&L / contract | 95% CI | Total | Verdict |
|---|--:|--:|--:|--:|--:|
| `fade_move` 18h | 7 | +13.1¢ | — | $+0.92 | collecting (7/100) |
| `fade_move` 24h | 4 | -5.3¢ | — | $-0.21 | collecting (4/100) |
| `fade_move` 30h | 4 | -16.0¢ | — | $-0.64 | collecting (4/100) |
| `fav_longshot` 18h | 30 | -8.8¢ | -28.2¢ to +9.1¢ | $-2.65 | collecting (30/100) |
| `fav_longshot` 24h | 42 | +1.4¢ | -15.6¢ to +17.8¢ | $+0.60 | collecting (42/100) |
| `fav_longshot` 30h | 25 | -6.8¢ | -24.1¢ to +10.8¢ | $-1.70 | collecting (25/100) |
| `follow_move` 18h | 7 | -14.0¢ | — | $-0.98 | collecting (7/100) |
| `follow_move` 24h | 5 | -5.2¢ | — | $-0.26 | collecting (5/100) |
| `follow_move` 30h | 1 | -16.0¢ | — | $-0.16 | collecting (1/100) |
| `overround` 18h | 1 | +7.0¢ | — | $+0.07 | collecting (1/100) |
| `overround` 24h | 3 | -21.3¢ | — | $-0.64 | collecting (3/100) |
| `overround` 30h | 2 | +28.5¢ | — | $+0.57 | collecting (2/100) |
| `rv_updown_3c` 6h | 2 | -79.0¢ | — | $-1.58 | collecting (2/100) |
| `rv_updown_6c` 6h | 2 | -76.0¢ | — | $-1.52 | collecting (2/100) |
| `sell_longshot` 6h | 14 | +3.0¢ | — | $+0.42 | collecting (14/100) |
| `sell_longshot` 12h | 1 | +9.0¢ | — | $+0.09 | collecting (1/100) |
| `sell_longshot_div` 6h | 25 | +7.0¢ | +6.4¢ to +7.5¢ | $+1.74 | collecting (25/100) |
| `sell_longshot_div` 24h | 16 | +4.1¢ | -5.9¢ to +12.3¢ | $+0.66 | collecting (16/100) |
| `tails` 18h | 6 | -15.3¢ | — | $-0.92 | collecting (6/100) |
| `tails` 24h | 5 | -8.0¢ | — | $-0.40 | collecting (5/100) |
| `tails` 30h | 2 | +13.0¢ | — | $+0.26 | collecting (2/100) |

## Daily reports

- [2026-11-04](paper/reports/2026-11-04.md)
- [2026-11-03](paper/reports/2026-11-03.md)
- [2026-11-02](paper/reports/2026-11-02.md)
- [2026-11-01](paper/reports/2026-11-01.md)
- [2026-10-31](paper/reports/2026-10-31.md)
