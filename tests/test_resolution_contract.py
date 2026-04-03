import json
from pathlib import Path

from pm_latency.domain.gamma_parse import event_to_traded_markets
from pm_latency.strategy.resolution_contract import contract_from_traded_market, infer_oracle_pair


def test_infer_oracle_from_fixture():
    raw = Path(__file__).parent / "fixtures" / "gamma_btc_15m_event.json"
    event = json.loads(raw.read_text())
    m = event_to_traded_markets(event)[0]
    assert infer_oracle_pair(m) == "BTC-USD"
    c = contract_from_traded_market(m)
    assert c.window_start_ts == m.window_start_ts
    assert c.window_end_ts == m.window_start_ts + m.window_seconds
    assert c.rule == "up_if_end_ge_start"
    assert "oracle" in c.resolution_hint.lower()
