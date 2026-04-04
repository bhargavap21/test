"""Risk limits from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _f(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _i(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(float(raw))


@dataclass(frozen=True, slots=True)
class RiskLimits:
    bankroll_usd: float
    max_total_exposure_usd: float
    max_market_exposure_usd: float
    max_order_notional_usd: float
    daily_loss_limit_usd: float
    kelly_fraction: float
    max_orders_per_minute: int


def limits_from_environ() -> RiskLimits:
    return RiskLimits(
        bankroll_usd=_f("BANKROLL_USD", 1000.0),
        max_total_exposure_usd=_f("MAX_NOTIONAL_USD", 500.0),
        max_market_exposure_usd=_f("MAX_MARKET_NOTIONAL_USD", 150.0),
        max_order_notional_usd=_f("MAX_ORDER_NOTIONAL_USD", 50.0),
        daily_loss_limit_usd=_f("DAILY_LOSS_LIMIT_USD", 100.0),
        kelly_fraction=_f("KELLY_FRACTION", 0.25),
        max_orders_per_minute=_i("MAX_ORDERS_PER_MINUTE", 30),
    )
