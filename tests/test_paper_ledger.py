import json
from pathlib import Path

import pytest

from pm_latency.paperdash.ledger import PaperLedger


def test_simulated_buy_and_settle(tmp_path: Path):
    db = tmp_path / "p.db"
    led = PaperLedger(db, taker_fee_bps=100, redeem_fee_bps=50)
    led.record_simulated_buy(
        condition_id="0xabc",
        event_slug="test",
        outcome="Up",
        token_id="tok1",
        contracts=10.0,
        entry_price=0.4,
        intent_id="i1",
        intent_key="k1",
    )
    open_f = led.open_fills()
    assert len(open_f) == 1
    fee_in = float(open_f[0]["fee_entry_usd"])
    assert fee_in == pytest.approx(10 * 0.4 * 0.01)

    market = {
        "conditionId": "0xabc",
        "closed": True,
        "outcomes": json.dumps(["Up", "Down"]),
        "outcomePrices": json.dumps(["1", "0"]),
    }
    n = led.settle_from_gamma_market(market)
    assert n == 1
    s = led.summary()
    assert s["open_trades"] == 0
    assert s["settled_trades"] == 1
    payout = 10.0
    fee_out = payout * 0.005
    cost = 10 * 0.4 + fee_in
    assert s["realized_pnl_usd"] == pytest.approx(payout - fee_out - cost)


def test_settle_loser(tmp_path: Path):
    db = tmp_path / "p2.db"
    led = PaperLedger(db, taker_fee_bps=0, redeem_fee_bps=0)
    led.record_simulated_buy(
        condition_id="0xl",
        event_slug="t",
        outcome="Up",
        token_id="t1",
        contracts=5.0,
        entry_price=0.5,
        intent_id="i",
        intent_key="k",
    )
    market = {
        "conditionId": "0xl",
        "closed": True,
        "outcomes": json.dumps(["Up", "Down"]),
        "outcomePrices": json.dumps(["0", "1"]),
    }
    led.settle_from_gamma_market(market)
    s = led.summary()
    assert s["realized_pnl_usd"] == pytest.approx(-2.5)


def test_settle_checksum_address_match(tmp_path: Path):
    """DB stores lower(); Gamma may return checksummed 0x."""
    db = tmp_path / "p4.db"
    led = PaperLedger(db)
    led.record_simulated_buy(
        condition_id="0xAbCdef0123456789abcdef0123456789abcdef12",
        event_slug="x",
        outcome="up",
        token_id="t",
        contracts=1.0,
        entry_price=0.5,
        intent_id="i",
        intent_key="k",
    )
    market = {
        "conditionId": "0xAbCdef0123456789abcdef0123456789abcdef12",
        "closed": True,
        "outcomes": json.dumps(["Up", "Down"]),
        "outcomePrices": json.dumps(["1", "0"]),
    }
    assert led.settle_from_gamma_market(market) == 1
    assert led.summary()["settled_trades"] == 1


def test_mtm(tmp_path: Path):
    db = tmp_path / "p3.db"
    led = PaperLedger(db)
    led.record_simulated_buy(
        condition_id="0xm",
        event_slug="m",
        outcome="Up",
        token_id="tid",
        contracts=10.0,
        entry_price=0.3,
        intent_id="i",
        intent_key="k",
    )
    led.update_quotes({"tid": (0.5, 0.52)})
    s = led.summary()
    assert s["unrealized_pnl_usd_estimate"] == pytest.approx(10 * 0.51 - 3.0)
