import pytest

from pm_latency.strategy.fair_value import (
    WindowFairValueState,
    build_outcome_quotes,
    prob_up_terminal,
)
from pm_latency.strategy.volatility import EwmaVol


def test_prob_up_terminal_at_expiry():
    p = prob_up_terminal(mid=100.0, anchor=100.0, tau_seconds=0.0, sigma_annual=0.5)
    assert p == 1.0
    p2 = prob_up_terminal(mid=99.0, anchor=100.0, tau_seconds=0.0, sigma_annual=0.5)
    assert p2 == 0.0


def test_prob_up_increases_with_spot():
    base = prob_up_terminal(mid=100.0, anchor=100.0, tau_seconds=60.0, sigma_annual=0.8)
    hi = prob_up_terminal(mid=101.0, anchor=100.0, tau_seconds=60.0, sigma_annual=0.8)
    assert hi > base


def test_prob_up_atm_decreases_with_time():
    """At spot==anchor, GBM log-normal correction lowers P(S_T >= K) as T grows."""
    p_short = prob_up_terminal(mid=100.0, anchor=100.0, tau_seconds=10.0, sigma_annual=1.0)
    p_long = prob_up_terminal(mid=100.0, anchor=100.0, tau_seconds=3600.0, sigma_annual=1.0)
    assert p_long < p_short


def test_window_state_edge_against_ask(monkeypatch):
    from pm_latency.domain.models import TradedMarket

    m = TradedMarket(
        condition_id="0x1",
        market_id="1",
        event_id="e",
        event_slug="btc-updown-15m-1000",
        market_slug="btc-updown-15m-1000",
        asset="btc",
        window_seconds=900,
        window_start_ts=1000,
        title="t",
        question="q",
        description="Chainlink BTC/USD stream btc-usd resolution.",
        resolution_source="https://data.chain.link/streams/btc-usd",
        tick_size=0.01,
        neg_risk=False,
        accepting_orders=True,
        closed=False,
        active=True,
        outcomes=("Up", "Down"),
        token_ids=("tok_up", "tok_dn"),
        end_date=None,
    )

    vol = EwmaVol(min_updates=1, half_life_seconds=60.0)
    st = WindowFairValueState(market=m, vol=vol, anchor_mid=100.0)

    monkeypatch.setattr("pm_latency.strategy.fair_value._now_ts", lambda: 1000.0 + 60.0)

    quotes = {
        "tok_up": (0.40, 0.42),
        "tok_dn": (0.58, 0.60),
    }
    snap = st.snapshot(cex_mid=101.0, cex_ts_ms=1_060_000, quotes_by_token=quotes)
    assert snap is not None
    assert snap.p_up > 0.5
    assert snap.edge_buy_vs_ask["Up"] == pytest.approx(snap.model_prob_by_outcome["Up"] - 0.42)


def test_build_outcome_quotes():
    from pm_latency.domain.models import TradedMarket

    m = TradedMarket(
        condition_id="0x1",
        market_id="1",
        event_id="e",
        event_slug="s",
        market_slug="s",
        asset="btc",
        window_seconds=300,
        window_start_ts=0,
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
        token_ids=("a", "b"),
        end_date=None,
    )
    q = build_outcome_quotes(m, {"a": (0.1, 0.2), "b": (0.8, 0.9)})
    assert q[0].outcome == "Up" and q[0].best_ask == 0.2
