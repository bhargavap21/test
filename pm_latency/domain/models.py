"""Shared datatypes for market metadata."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TradedMarket:
    """One CLOB-tradable market (condition) plus event context."""

    condition_id: str
    market_id: str
    event_id: str
    event_slug: str
    market_slug: str
    asset: str  # "btc" | "eth"
    window_seconds: int  # 300 or 900
    window_start_ts: int
    title: str
    question: str
    description: str
    resolution_source: str
    tick_size: float
    neg_risk: bool
    accepting_orders: bool
    closed: bool
    active: bool
    outcomes: tuple[str, ...]
    token_ids: tuple[str, ...]
    end_date: str | None
