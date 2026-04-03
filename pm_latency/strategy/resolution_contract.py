"""Structured view of Polymarket resolution text for short Up/Down crypto windows."""

from __future__ import annotations

from dataclasses import dataclass

from pm_latency.domain.models import TradedMarket


@dataclass(frozen=True, slots=True)
class ResolutionContract:
    """What we rely on for fair value (oracle identity + window bounds)."""

    window_start_ts: int
    window_end_ts: int
    oracle_pair: str | None  # e.g. "BTC-USD" when Chainlink BTC/USD is cited
    rule: str  # "up_if_end_ge_start" per Polymarket copy for these markets
    resolution_hint: str  # short human-readable note


def infer_oracle_pair(market: TradedMarket) -> str | None:
    blob = f"{market.resolution_source}\n{market.description}".lower()
    if "btc-usd" in blob or "btc/usd" in blob or "streams/btc-usd" in blob:
        return "BTC-USD"
    if "eth-usd" in blob or "eth/usd" in blob or "streams/eth-usd" in blob:
        return "ETH-USD"
    return None


def contract_from_traded_market(market: TradedMarket) -> ResolutionContract:
    start = market.window_start_ts
    end = start + market.window_seconds
    pair = infer_oracle_pair(market)
    hint = (
        "Settlement uses the cited oracle stream, not necessarily Binance spot. "
        "Use CEX as a fast proxy only; validate against the oracle feed for production."
    )
    return ResolutionContract(
        window_start_ts=start,
        window_end_ts=end,
        oracle_pair=pair,
        rule="up_if_end_ge_start",
        resolution_hint=hint,
    )
