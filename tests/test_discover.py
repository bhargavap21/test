from pm_latency.ops import discover as discover_mod


def test_discover_uses_fetch_and_parses(monkeypatch):
    import json
    from pathlib import Path

    raw = Path(__file__).parent / "fixtures" / "gamma_btc_15m_event.json"
    event = json.loads(raw.read_text())

    def fake_fetch(base: str, slug: str, timeout_s: float = 30.0):
        assert "gamma-api" in base
        if slug == "btc-updown-15m-1775065500":
            return [event]
        return []

    monkeypatch.setattr(discover_mod, "fetch_events_by_slug", fake_fetch)

    rows = list(
        discover_mod.discover_short_crypto_markets(
            gamma_base="https://gamma-api.polymarket.com",
            now_ts=1775065500,
            assets=("btc",),
            windows=(900,),
        )
    )
    assert len(rows) == 1
    assert rows[0].event_slug == "btc-updown-15m-1775065500"
