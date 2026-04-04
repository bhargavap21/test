import json
from datetime import date
from pathlib import Path

import pytest

from pm_latency.risk.config import RiskLimits
from pm_latency.risk.engine import OrderRequest, RiskEngine


@pytest.fixture
def limits_tight() -> RiskLimits:
    return RiskLimits(
        bankroll_usd=1000.0,
        max_total_exposure_usd=100.0,
        max_market_exposure_usd=80.0,
        max_order_notional_usd=50.0,
        daily_loss_limit_usd=50.0,
        kelly_fraction=0.25,
        max_orders_per_minute=2,
    )


def test_allows_edge_and_sizes(tmp_path: Path, limits_tight: RiskLimits):
    state = tmp_path / "rs.json"
    eng = RiskEngine(limits_tight, state_path=state, kill_file=tmp_path / "no_kill")
    req = OrderRequest(
        condition_id="0xa",
        token_id="t",
        outcome="Up",
        model_prob=0.6,
        ask_price=0.5,
    )
    d = eng.evaluate(req)
    assert d.allowed
    assert d.reason == "ok"
    assert d.notional_usd == pytest.approx(50.0)
    assert d.contracts == pytest.approx(100.0)


def test_blocks_no_edge(tmp_path: Path, limits_tight: RiskLimits):
    eng = RiskEngine(limits_tight, state_path=tmp_path / "rs.json", kill_file=tmp_path / "k")
    req = OrderRequest("0xa", "t", "Up", 0.5, 0.5)
    d = eng.evaluate(req)
    assert not d.allowed
    assert d.reason == "no_edge_or_invalid_prices"


def test_blocks_market_exposure(tmp_path: Path, limits_tight: RiskLimits):
    state = tmp_path / "rs.json"
    state.write_text(
        json.dumps(
            {
                "day_utc": date.today().isoformat(),
                "daily_realized_pnl_usd": 0.0,
                "exposure_usd_by_condition": {"0xa": 75.0},
                "order_timestamps_unix": [],
            }
        ),
        encoding="utf-8",
    )
    eng = RiskEngine(limits_tight, state_path=state, kill_file=tmp_path / "nk")
    req = OrderRequest("0xa", "t", "Up", 0.6, 0.5)
    d = eng.evaluate(req)
    assert not d.allowed
    assert d.reason == "max_market_exposure"


def test_blocks_kill_file(tmp_path: Path, limits_tight: RiskLimits):
    k = tmp_path / "kill"
    k.write_text("1")
    eng = RiskEngine(limits_tight, state_path=tmp_path / "rs.json", kill_file=k)
    d = eng.evaluate(OrderRequest("0xa", "t", "Up", 0.6, 0.5))
    assert not d.allowed
    assert d.reason == "kill_switch"


def test_rate_limit(tmp_path: Path, limits_tight: RiskLimits, monkeypatch: pytest.MonkeyPatch):
    state = tmp_path / "rs.json"
    now = 1_700_000_000.0
    state.write_text(
        json.dumps(
            {
                "day_utc": date.today().isoformat(),
                "daily_realized_pnl_usd": 0.0,
                "exposure_usd_by_condition": {},
                "order_timestamps_unix": [now, now + 1],
            }
        ),
        encoding="utf-8",
    )
    eng = RiskEngine(limits_tight, state_path=state, kill_file=tmp_path / "nk")

    import pm_latency.risk.engine as eng_mod

    monkeypatch.setattr(eng_mod, "now_unix", lambda: now + 5.0)

    d = eng.evaluate(OrderRequest("0xa", "t", "Up", 0.6, 0.5))
    assert not d.allowed
    assert d.reason == "rate_limit_orders_per_minute"


def test_daily_loss_limit(tmp_path: Path, limits_tight: RiskLimits):
    state = tmp_path / "rs.json"
    state.write_text(
        json.dumps(
            {
                "day_utc": date.today().isoformat(),
                "daily_realized_pnl_usd": -60.0,
                "exposure_usd_by_condition": {},
                "order_timestamps_unix": [],
            }
        ),
        encoding="utf-8",
    )
    eng = RiskEngine(limits_tight, state_path=state, kill_file=tmp_path / "nk")
    d = eng.evaluate(OrderRequest("0xa", "t", "Up", 0.6, 0.5))
    assert not d.allowed
    assert d.reason == "daily_loss_limit"
