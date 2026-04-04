import json
from pathlib import Path

from pm_latency.domain.gamma_parse import event_to_traded_markets
from pm_latency.domain.registry import MarketRegistry


def test_registry_upsert(tmp_path):
    raw = Path(__file__).parent / "fixtures" / "gamma_btc_15m_event.json"
    event = json.loads(raw.read_text())
    rows = event_to_traded_markets(event)

    db = tmp_path / "markets.db"
    reg = MarketRegistry(db)
    assert reg.count() == 0
    n = reg.upsert_many(rows)
    assert n == 1
    assert reg.count() == 1

    n2 = reg.upsert_many(rows)
    assert n2 == 1
    assert reg.count() == 1
