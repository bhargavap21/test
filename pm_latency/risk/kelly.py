"""Fractional Kelly sizing for binary contracts priced in [0, 1]."""

from __future__ import annotations

import math


def full_kelly_fraction_binary(*, model_prob: float, ask_price: float) -> float | None:
    """
    Optimal fraction of bankroll for a one-shot binary buy at ask `c`.

    f* = (p - c) / (1 - c) for profit 1-c on win, loss c on lose, stake c.
    Returns None if undefined or no positive edge.
    """
    if not (0.0 < ask_price < 1.0):
        return None
    p = model_prob
    if not (0.0 <= p <= 1.0) or math.isnan(p):
        return None
    c = ask_price
    denom = 1.0 - c
    if denom < 1e-12:
        return None
    f_star = (p - c) / denom
    if f_star <= 0:
        return None
    return float(f_star)


def fractional_kelly_notional(
    *,
    bankroll_usd: float,
    model_prob: float,
    ask_price: float,
    kelly_fraction: float,
    max_order_notional_usd: float,
) -> float:
    """Dollar stake (notional) after Kelly and hard cap."""
    if bankroll_usd <= 0 or kelly_fraction <= 0:
        return 0.0
    f_star = full_kelly_fraction_binary(model_prob=model_prob, ask_price=ask_price)
    if f_star is None:
        return 0.0
    f = min(f_star * kelly_fraction, 1.0)
    raw = f * bankroll_usd
    return float(min(raw, max_order_notional_usd))
