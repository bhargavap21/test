"""Run CEX spot feed: Binance, Coinbase, or auto (Binance then Coinbase on failure)."""

from __future__ import annotations

import asyncio
import sys

from pm_latency.connectors.binance_ws import DEFAULT_BINANCE_WS, run_binance_book_ticker
from pm_latency.connectors.coinbase_ws import (
    DEFAULT_COINBASE_WS,
    asset_to_coinbase_product,
    run_coinbase_ticker,
)
from pm_latency.domain.cex_symbols import collect_token_ids_and_binance_symbols
from pm_latency.domain.models import TradedMarket


def coinbase_products_for_rows(rows: list[TradedMarket]) -> tuple[str, ...]:
    assets: set[str] = {r.asset for r in rows}
    return tuple(asset_to_coinbase_product(a) for a in sorted(assets))


async def run_cex_feed(
    *,
    provider: str,
    rows: list[TradedMarket],
    binance_ws: str,
    coinbase_ws: str,
    on_tick,
    stop: asyncio.Event,
) -> None:
    """
    provider: binance | coinbase | auto

    auto: try Binance; on failure log and run Coinbase until stop.
    """
    _token_ids, binance_symbols = collect_token_ids_and_binance_symbols(rows)
    products = coinbase_products_for_rows(rows)
    prov = provider.strip().lower()
    if prov not in ("binance", "coinbase", "auto"):
        raise ValueError(f"unknown cex provider: {provider!r}")

    async def _binance() -> None:
        await run_binance_book_ticker(
            ws_base=binance_ws,
            symbols=binance_symbols,
            on_tick=on_tick,
            stop=stop,
        )

    async def _coinbase() -> None:
        await run_coinbase_ticker(
            ws_url=coinbase_ws,
            product_ids=products,
            on_tick=on_tick,
            stop=stop,
        )

    if prov == "binance":
        await _binance()
        return
    if prov == "coinbase":
        await _coinbase()
        return

    try:
        await _binance()
    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(
            f"cex: Binance failed ({type(e).__name__}: {e}); falling back to Coinbase",
            file=sys.stderr,
        )
    if stop.is_set():
        return
    await _coinbase()


__all__ = [
    "DEFAULT_BINANCE_WS",
    "DEFAULT_COINBASE_WS",
    "coinbase_products_for_rows",
    "run_cex_feed",
]
