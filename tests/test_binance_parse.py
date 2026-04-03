import time

import pytest

from pm_latency.connectors.binance_ws import book_ticker_stream_path, parse_book_ticker_payload


def test_book_ticker_stream_path():
    p = book_ticker_stream_path(("BTCUSDT", "ETHUSDT"))
    assert p == "btcusdt@bookTicker/ethusdt@bookTicker"


def test_parse_book_ticker():
    recv_ns = time.monotonic_ns()
    inner = {
        "e": "bookTicker",
        "u": 400900217,
        "s": "BTCUSDT",
        "b": "0.0024",
        "B": "10",
        "a": "0.0026",
        "A": "100",
        "E": 1_609_000_000_123,
    }
    t = parse_book_ticker_payload(inner, recv_ns)
    assert t is not None
    assert t.source == "cex"
    assert t.symbol == "BTCUSDT"
    assert t.ts_exchange_ms == 1_609_000_000_123
    assert t.best_bid == 0.0024
    assert t.best_ask == 0.0026
    assert t.mid == pytest.approx((0.0024 + 0.0026) / 2)
