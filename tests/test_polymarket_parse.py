import json
import time

import pytest

from pm_latency.connectors.polymarket_ws import parse_polymarket_message


def test_best_bid_ask():
    recv_ns = time.monotonic_ns()
    msg = {
        "event_type": "best_bid_ask",
        "market": "0xabc",
        "asset_id": "12345",
        "best_bid": "0.48",
        "best_ask": "0.52",
        "spread": "0.04",
        "timestamp": "1757908892351",
    }
    ticks = parse_polymarket_message(json.dumps(msg), recv_ns)
    assert len(ticks) == 1
    t = ticks[0]
    assert t.source == "polymarket"
    assert t.symbol == "12345"
    assert t.best_bid == 0.48
    assert t.best_ask == 0.52
    assert t.mid == pytest.approx(0.50)
    assert t.ts_exchange_ms == 1_757_908_892_351


def test_book_top():
    recv_ns = time.monotonic_ns()
    msg = {
        "event_type": "book",
        "asset_id": "99",
        "bids": [{"price": ".48", "size": "30"}, {"price": ".49", "size": "1"}],
        "asks": [{"price": ".52", "size": "25"}, {"price": ".53", "size": "1"}],
        "timestamp": "1000000000",
    }
    ticks = parse_polymarket_message(json.dumps(msg), recv_ns)
    assert len(ticks) == 1
    t = ticks[0]
    assert t.best_bid == 0.49
    assert t.best_ask == 0.52
    assert t.ts_exchange_ms == 1_000_000_000_000


def test_pong_empty():
    recv_ns = time.monotonic_ns()
    assert parse_polymarket_message("PONG", recv_ns) == []
    assert parse_polymarket_message("", recv_ns) == []
