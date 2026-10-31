"""Kalshi public read API plus the small parsing helpers every script needs."""
import json, time, urllib.parse, urllib.request
from datetime import datetime

BASE = "https://api.elections.kalshi.com/trade-api/v2"
MONTHS = dict(JAN=1, FEB=2, MAR=3, APR=4, MAY=5, JUN=6, JUL=7, AUG=8, SEP=9, OCT=10, NOV=11, DEC=12)


def get(path, **params):
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{url}: {err}")


def fnum(x):
    """float(x), or None for empty / non-numeric values like an expiration_value of "70° to 71°"."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def iso_ts(s):
    """Epoch seconds of an ISO-8601 UTC string. Drops fractions: Python 3.9 rejects Kalshi's 5-digit ones."""
    return datetime.fromisoformat(s[:19] + "+00:00").timestamp()


def edate(ev):
    """Settlement date (YYYY-MM-DD) from an event ticker suffix such as KXHIGHNY-25OCT30."""
    s = ev.split("-")[-1]
    return f"20{s[:2]}-{MONTHS[s[2:5]]:02d}-{s[5:7]}"
