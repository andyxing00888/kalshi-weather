"""Kalshi fee schedule per contract, rounded up to the cent."""
import math


def fee(p):
    """Taker fee."""
    return math.ceil(0.07 * p * (1 - p) * 100) / 100


def mfee(p):
    """Maker fee."""
    return math.ceil(0.0175 * p * (1 - p) * 100) / 100
