from pathlib import Path

from pm_latency.domain.models import TradedMarket
from pm_latency.ops.paper_eval import (
    candidates_from_snapshot_and_quotes,
    finalize_candidates_with_risk,
    stable_intent_key,
)
from pm_latency.risk.config import RiskLimits
from pm_latency.risk.engine import RiskEngine
from pm_latency.strategy.fair_value import EdgeEstimate
from pm_latency.strategy.resolution_contract import contract_from_traded_market


def _market() -> TradedMarket:
    return TradedMarket(
        condition_id="0xc1",
        market_id="1",
        event_id="e",
        event_slug="btc-updown-15m-1000",
        market_slug="btc-updown-15m-1000",
        asset="btc",
        window_seconds=900,
        window_start_ts=1000,
        title="t",
        question="q",
        description="btc-usd chainlink",
        resolution_source="https://data.chain.link/streams/btc-usd",
        tick_size=0.01,
        neg_risk=False,
        accepting_orders=True,
        closed=False,
        active=True,
        outcomes=("Up", "Down"),
        token_ids=("tok_u", "tok_d"),
        end_date=None,
    )


def test_stable_intent_key_deterministic():
    k1 = stable_intent_key(
        condition_id="0x1",
        token_id="a",
        outcome="Up",
        ask_price=0.5,
        model_prob=0.55,
    )
    k2 = stable_intent_key(
        condition_id="0x1",
        token_id="a",
        outcome="Up",
        ask_price=0.5,
        model_prob=0.55,
    )
    assert k1 == k2
    assert len(k1) == 24


def test_candidates_min_edge():
    m = _market()
    c = contract_from_traded_market(m)
    snap = EdgeEstimate(
        market=m,
        contract=c,
        now_ts=2000.0,
        cex_mid=100.0,
        anchor_mid=99.0,
        sigma_annual=0.5,
        tau_seconds=100.0,
        p_up=0.55,
        outcomes=m.outcomes,
        model_prob_by_outcome={"Up": 0.55, "Down": 0.45},
        edge_buy_vs_ask={"Up": 0.05, "Down": -0.05},
    )
    quotes = {"tok_u": (0.48, 0.50), "tok_d": (0.48, 0.50)}
    cand = candidates_from_snapshot_and_quotes(snap, quotes, min_edge=0.02)
    assert len(cand) == 1
    assert cand[0].outcome == "Up"


def test_finalize_records_rate_limit(tmp_path: Path):
    limits = RiskLimits(
        bankroll_usd=1000.0,
        max_total_exposure_usd=500.0,
        max_market_exposure_usd=200.0,
        max_order_notional_usd=50.0,
        daily_loss_limit_usd=100.0,
        kelly_fraction=0.25,
        max_orders_per_minute=1,
    )
    risk = RiskEngine(limits, state_path=tmp_path / "rs.json", kill_file=tmp_path / "nk")
    m = _market()
    c = contract_from_traded_market(m)
    snap = EdgeEstimate(
        market=m,
        contract=c,
        now_ts=2000.0,
        cex_mid=100.0,
        anchor_mid=99.0,
        sigma_annual=0.5,
        tau_seconds=100.0,
        p_up=0.6,
        outcomes=m.outcomes,
        model_prob_by_outcome={"Up": 0.6, "Down": 0.4},
        edge_buy_vs_ask={},
    )
    quotes = {"tok_u": (0.45, 0.50), "tok_d": (0.30, 0.35)}
    cand = candidates_from_snapshot_and_quotes(snap, quotes, min_edge=0.01)
    assert len(cand) == 2
    intents = finalize_candidates_with_risk(risk, cand)
    allowed = [i for i in intents if i.risk.allowed]
    blocked = [i for i in intents if not i.risk.allowed]
    assert len(allowed) == 1
    assert len(blocked) == 1
    assert blocked[0].risk.reason == "rate_limit_orders_per_minute"
