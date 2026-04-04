"""Normalized cross-venue price ticks for latency measurement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Source = Literal["cex", "polymarket"]


@dataclass(frozen=True, slots=True)
class MarketTick:
    """Single observable price point with receive time for lag analysis."""

    source: Source
    venue: str  # e.g. "binance", "polymarket_clob"
    symbol: str  # e.g. "BTCUSDT" or clob token_id
    ts_exchange_ms: int | None  # venue timestamp when known (ms)
    ts_recv_ns: int  # time.monotonic_ns() at receive (local)
    best_bid: float | None
    best_ask: float | None
    mid: float | None
    raw_event_type: str | None = None  # e.g. "bookTicker", "best_bid_ask"
