"""Paper-fill rule for resting maker orders."""
from .api import fnum
from .fees import mfee

FILL_WINDOW = 6  # hours an order rests


def fill_pnl(side, px, y, candles, t0):
    """P&L per contract if the resting order filled, else None.
    Filled only when a trade printed strictly through px within FILL_WINDOW hours of t0."""
    after = [c for c in candles if t0 < c["end_period_ts"] <= t0 + FILL_WINDOW * 3600]
    if side == "buy_yes":
        if not any((fnum(c["price"].get("low_dollars")) or 1) < px for c in after):
            return None
        return y - px - mfee(px)
    if not any((fnum(c["price"].get("high_dollars")) or 0) > px for c in after):
        return None
    return px - y - mfee(1 - px)
