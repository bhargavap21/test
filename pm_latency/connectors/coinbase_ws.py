"""Coinbase Exchange WebSocket ticker channel (public BTC-USD / ETH-USD)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

import websockets

from pm_latency.domain.ticks import MarketTick

logger = logging.getLogger(__name__)

DEFAULT_COINBASE_WS = "wss://ws-feed.exchange.coinbase.com"


def asset_to_coinbase_product(asset: str) -> str:
    a = asset.lower().strip()
    if a == "btc":
        return "BTC-USD"
    if a == "eth":
        return "ETH-USD"
    raise ValueError(f"unsupported asset for Coinbase: {asset!r}")


def parse_coinbase_ticker(msg: dict, recv_ns: int) -> MarketTick | None:
    if str(msg.get("type") or "") != "ticker":
        return None
    pid = str(msg.get("product_id") or "")
    bid = _f(msg.get("best_bid"))
    ask = _f(msg.get("best_ask"))
    mid = (bid + ask) / 2.0 if bid is not None and ask is not None else None
    ts_ms = _iso_ms(str(msg.get("time") or ""))
    return MarketTick(
        source="cex",
        venue="coinbase",
        symbol=pid,
        ts_exchange_ms=ts_ms,
        ts_recv_ns=recv_ns,
        best_bid=bid,
        best_ask=ask,
        mid=mid,
        raw_event_type="ticker",
    )


async def run_coinbase_ticker(
    *,
    ws_url: str,
    product_ids: tuple[str, ...],
    on_tick: Callable[[MarketTick], Awaitable[None] | None],
    stop: asyncio.Event,
) -> None:
    if not product_ids:
        raise ValueError("product_ids required")
    sub = {
        "type": "subscribe",
        "product_ids": list(product_ids),
        "channels": ["ticker"],
    }
    payload = json.dumps(sub)
    url = ws_url.rstrip("/")

    logger.info("coinbase: connecting %s products=%s", url, product_ids)
    async with websockets.connect(
        url,
        ping_interval=20,
        ping_timeout=60,
        close_timeout=5,
    ) as ws:
        await ws.send(payload)
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
            if not isinstance(msg, dict):
                continue
            tick = parse_coinbase_ticker(msg, recv_ns)
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


def _iso_ms(s: str) -> int | None:
    if not s.strip():
        return None
    try:
        t = s.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except ValueError:
        return None
