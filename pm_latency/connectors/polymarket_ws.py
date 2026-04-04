"""Polymarket CLOB market channel WebSocket (public order book / best bid-ask)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

import websockets

from pm_latency.domain.ticks import MarketTick

logger = logging.getLogger(__name__)

DEFAULT_CLOB_MARKET_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

PING_INTERVAL_S = 10.0


def parse_polymarket_message(
    text: str,
    recv_ns: int,
) -> list[MarketTick]:
    """Turn one WS text frame into zero or more MarketTicks."""
    t = text.strip()
    if t.upper() == "PONG" or t == "":
        return []
    try:
        msg: Any = json.loads(t)
    except json.JSONDecodeError:
        return []

    if isinstance(msg, list):
        out: list[MarketTick] = []
        for item in msg:
            if isinstance(item, dict):
                out.extend(_ticks_from_obj(item, recv_ns))
        return out

    if isinstance(msg, dict):
        return _ticks_from_obj(msg, recv_ns)

    return []


def _ticks_from_obj(msg: dict[str, Any], recv_ns: int) -> list[MarketTick]:
    et = str(msg.get("event_type") or "")

    if et == "best_bid_ask":
        t = _one_best_bid_ask(msg, recv_ns)
        return [t] if t else []

    if et == "book":
        t = _one_book_top(msg, recv_ns)
        return [t] if t else []

    return []


def _one_best_bid_ask(msg: dict[str, Any], recv_ns: int) -> MarketTick | None:
    aid = str(msg.get("asset_id") or "")
    if not aid:
        return None
    bid = _f(msg.get("best_bid"))
    ask = _f(msg.get("best_ask"))
    mid = (bid + ask) / 2.0 if bid is not None and ask is not None else None
    ts_ms = _parse_ts_ms(msg.get("timestamp"))
    return MarketTick(
        source="polymarket",
        venue="polymarket_clob",
        symbol=aid,
        ts_exchange_ms=ts_ms,
        ts_recv_ns=recv_ns,
        best_bid=bid,
        best_ask=ask,
        mid=mid,
        raw_event_type="best_bid_ask",
    )


def _one_book_top(msg: dict[str, Any], recv_ns: int) -> MarketTick | None:
    aid = str(msg.get("asset_id") or "")
    if not aid:
        return None
    bids = msg.get("bids")
    asks = msg.get("asks")
    bid = _top_book_side(bids, is_bid=True)
    ask = _top_book_side(asks, is_bid=False)
    mid = (bid + ask) / 2.0 if bid is not None and ask is not None else None
    ts_ms = _parse_ts_ms(msg.get("timestamp"))
    return MarketTick(
        source="polymarket",
        venue="polymarket_clob",
        symbol=aid,
        ts_exchange_ms=ts_ms,
        ts_recv_ns=recv_ns,
        best_bid=bid,
        best_ask=ask,
        mid=mid,
        raw_event_type="book",
    )


def _top_book_side(levels: object, *, is_bid: bool) -> float | None:
    if not isinstance(levels, list) or not levels:
        return None
    best: float | None = None
    for lv in levels:
        if not isinstance(lv, dict):
            continue
        p = _f(lv.get("price"))
        if p is None:
            continue
        if best is None:
            best = p
        elif is_bid:
            best = max(best, p)
        else:
            best = min(best, p)
    return best


def _parse_ts_ms(v: object) -> int | None:
    if v is None:
        return None
    try:
        n = int(str(v).strip())
    except ValueError:
        return None
    # Docs show ms; if value looks like seconds, scale up
    if n < 10**12:
        return n * 1000
    return n


def _f(v: object) -> float | None:
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s == "0":
        return None
    try:
        return float(s)
    except ValueError:
        return None


async def run_polymarket_market_ws(
    *,
    ws_url: str,
    token_ids: tuple[str, ...],
    on_tick: Callable[[MarketTick], Awaitable[None] | None],
    stop: asyncio.Event,
) -> None:
    if not token_ids:
        raise ValueError("token_ids required for Polymarket subscription")

    sub = {
        "assets_ids": list(token_ids),
        "type": "market",
        "custom_feature_enabled": True,
    }
    payload = json.dumps(sub)

    logger.info("polymarket: connecting %s (%d assets)", ws_url, len(token_ids))

    async with websockets.connect(
        ws_url,
        ping_interval=None,
        close_timeout=5,
    ) as ws:
        await ws.send(payload)

        ping_task = asyncio.create_task(_ping_loop(ws, stop))

        try:
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
                if not isinstance(raw, str):
                    continue

                if raw.strip().upper() == "PONG":
                    continue

                for tick in parse_polymarket_message(raw, recv_ns):
                    r = on_tick(tick)
                    if asyncio.iscoroutine(r):
                        await r
        finally:
            ping_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ping_task


async def _ping_loop(ws: object, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await asyncio.sleep(PING_INTERVAL_S)
            await ws.send("PING")
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("polymarket: ping failed")
            break
