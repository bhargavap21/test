from pathlib import Path

from pm_latency.risk.state import RiskState, load_risk_state, save_risk_state


def test_save_load_roundtrip(tmp_path: Path):
    p = tmp_path / "r.json"
    st = RiskState()
    st.daily_realized_pnl_usd = -10.0
    st.exposure_usd_by_condition["0x1"] = 25.0
    save_risk_state(p, st)
    st2 = load_risk_state(p)
    assert st2.daily_realized_pnl_usd == -10.0
    assert st2.exposure_usd_by_condition["0x1"] == 25.0


def test_prune_order_times():
    from pm_latency.risk.state import prune_order_times

    now = 1000.0
    t = prune_order_times([900.0, 950.0, 999.0], now=now, window_s=60.0)
    assert t == [950.0, 999.0]
