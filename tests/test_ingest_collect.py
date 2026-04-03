from pm_latency.domain.models import TradedMarket
from pm_latency.ops.ingest import _collect_tokens_and_symbols


def _row(asset: str, tokens: tuple[str, ...]) -> TradedMarket:
    return TradedMarket(
        condition_id="0x1",
        market_id="m1",
        event_id="e1",
        event_slug="btc-updown-15m-1",
        market_slug="btc-updown-15m-1",
        asset=asset,
        window_seconds=900,
        window_start_ts=1,
        title="t",
        question="q",
        description="d",
        resolution_source="r",
        tick_size=0.01,
        neg_risk=False,
        accepting_orders=True,
        closed=False,
        active=True,
        outcomes=("Up", "Down"),
        token_ids=tokens,
        end_date=None,
    )


def test_collect_dedupes_and_sorts_symbols():
    rows = [
        _row("btc", ("a", "b")),
        _row("eth", ("c", "d")),
        _row("btc", ("a", "b")),
    ]
    tokens, syms = _collect_tokens_and_symbols(rows)
    assert syms == ("BTCUSDT", "ETHUSDT")
    assert tokens == ("a", "b", "c", "d")
