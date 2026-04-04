import json
from pathlib import Path

from pm_latency.domain.gamma_parse import event_to_traded_markets


def test_event_to_traded_markets_fixture():
    raw = Path(__file__).parent / "fixtures" / "gamma_btc_15m_event.json"
    event = json.loads(raw.read_text())
    rows = event_to_traded_markets(event)
    assert len(rows) == 1
    m = rows[0]
    assert m.asset == "btc"
    assert m.window_seconds == 900
    assert m.window_start_ts == 1775065500
    assert m.condition_id.startswith("0x")
    assert m.outcomes == ("Up", "Down")
    assert len(m.token_ids) == 2
    assert "chain.link" in m.resolution_source.lower()
