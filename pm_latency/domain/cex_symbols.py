"""Map registry assets to CEX instrument names."""

from __future__ import annotations

from pm_latency.domain.models import TradedMarket


def asset_to_binance_symbol(asset: str) -> str:
    a = asset.lower().strip()
    if a == "btc":
        return "BTCUSDT"
    if a == "eth":
        return "ETHUSDT"
    raise ValueError(f"unsupported registry asset for CEX: {asset!r}")


def collect_token_ids_and_binance_symbols(
    rows: list[TradedMarket],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Unique token ids (order preserved) and Binance symbols for those assets."""
    token_ids: list[str] = []
    seen: set[str] = set()
    assets: set[str] = set()
    for r in rows:
        assets.add(r.asset)
        for tid in r.token_ids:
            if tid not in seen:
                seen.add(tid)
                token_ids.append(str(tid))
    symbols = tuple(asset_to_binance_symbol(a) for a in sorted(assets))
    return tuple(token_ids), symbols
