import time

import pytest

from pm_latency.connectors.coinbase_ws import asset_to_coinbase_product, parse_coinbase_ticker


def test_asset_to_product():
    assert asset_to_coinbase_product("btc") == "BTC-USD"
    assert asset_to_coinbase_product("ETH") == "ETH-USD"


def test_parse_ticker():
    recv_ns = time.monotonic_ns()
    msg = {
        "type": "ticker",
        "sequence": 1,
        "product_id": "BTC-USD",
        "price": "50000",
        "open_24h": "49000",
        "volume_24h": "100",
        "low_24h": "48000",
        "high_24h": "51000",
        "volume_30d": "1000",
        "best_bid": "49999",
        "best_ask": "50001",
        "side": "buy",
        "time": "2026-01-01T12:00:00.123Z",
        "trade_id": 1,
        "last_size": "0.01",
    }
    t = parse_coinbase_ticker(msg, recv_ns)
    assert t is not None
    assert t.venue == "coinbase"
    assert t.symbol == "BTC-USD"
    assert t.mid == pytest.approx(50000.0)
    assert t.ts_exchange_ms is not None
