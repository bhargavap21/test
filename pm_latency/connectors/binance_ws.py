"""Binance spot WebSocket book ticker (combined stream)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable

import websockets

from pm_latency.domain.ticks import MarketTick

logger = logging.getLogger(__name__)

DEFAULT_BINANCE_WS = "wss://stream.binance.com:9443/stream"


def book_ticker_stream_path(assets: tuple[str, ...]) -> str:
    """Build /stream?streams=a@bookTicker/b@bookTicker (lowercase symbols)."""
    parts = [f"{a.lower().strip()}@bookTicker" for a in assets if a.strip()]
    if not parts:
        raise ValueError("at least one asset symbol required")
    return "/".join(parts)


def parse_book_ticker_payload(data: dict, recv_ns: int) -> MarketTick | None:
    """Parse inner bookTicker object from combined stream wrapper."""
    if data.get("e") != "bookTicker":
        return None
    sym = str(data.get("s") or "")
    bid = _f(data.get("b"))
    ask = _f(data.get("a"))
    mid = (bid + ask) / 2.0 if bid is not None and ask is not None else None
    ts_ms = _i(data.get("E"))
    return MarketTick(
        source="cex",
        venue="binance",
        symbol=sym,
        ts_exchange_ms=ts_ms,
        ts_recv_ns=recv_ns,
        best_bid=bid,
        best_ask=ask,
        mid=mid,
        raw_event_type="bookTicker",
    )


async def run_binance_book_ticker(
    *,
    ws_base: str,
    symbols: tuple[str, ...],
    on_tick: Callable[[MarketTick], Awaitable[None] | None],
    stop: asyncio.Event,
) -> None:
    streams = book_ticker_stream_path(symbols)
    root = ws_base.rstrip("/")
    url = root if "streams=" in root else f"{root}?streams={streams}"

    logger.info("binance: connecting %s", url)
    async with websockets.connect(
        url,
        ping_interval=20,
        ping_timeout=60,
        close_timeout=5,
    ) as ws:
        while not stop.is_set():
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=30.0)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                raise
            recv_ns = time.monotonic_ns()
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            inner = msg.get("data") if isinstance(msg.get("data"), dict) else msg
            if not isinstance(inner, dict):
                continue
            tick = parse_book_ticker_payload(inner, recv_ns)
            if tick is None:
                continue
            r = on_tick(tick)
            if asyncio.iscoroutine(r):
                await r


def _f(v: object) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v))
    except ValueError:
        return None


def _i(v: object) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
