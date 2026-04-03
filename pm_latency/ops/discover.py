"""Refresh local registry by probing Gamma for short crypto Up/Down events."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator, Sequence

from pm_latency.connectors.gamma import DEFAULT_GAMMA_BASE, fetch_events_by_slug
from pm_latency.domain.gamma_parse import event_to_traded_markets
from pm_latency.domain.models import TradedMarket
from pm_latency.domain.registry import MarketRegistry
from pm_latency.domain.short_crypto import (
    WINDOW_5M,
    WINDOW_15M,
    Asset,
    build_event_slug,
    candidate_window_starts,
)


def discover_short_crypto_markets(
    *,
    gamma_base: str = DEFAULT_GAMMA_BASE,
    now_ts: int | None = None,
    assets: Sequence[Asset] = ("btc", "eth"),
    windows: Sequence[int] = (WINDOW_5M, WINDOW_15M),
) -> Iterator[TradedMarket]:
    """Yield `TradedMarket` rows for slugs that exist on Gamma (network I/O)."""
    ts = int(time.time()) if now_ts is None else int(now_ts)
    for asset in assets:
        for window_seconds in windows:
            for start in candidate_window_starts(ts, window_seconds):
                slug = build_event_slug(asset, window_seconds, start)
                events = fetch_events_by_slug(gamma_base, slug)
                for ev in events:
                    yield from event_to_traded_markets(ev)


def refresh_registry(
    registry: MarketRegistry,
    *,
    gamma_base: str | None = None,
    now_ts: int | None = None,
) -> int:
    """Probe Gamma and upsert all matching markets; returns rows written."""
    base = gamma_base or os.environ.get("GAMMA_API_BASE", DEFAULT_GAMMA_BASE)
    rows = list(discover_short_crypto_markets(gamma_base=base, now_ts=now_ts))
    return registry.upsert_many(rows)
