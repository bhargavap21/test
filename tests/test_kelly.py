import pytest

from pm_latency.risk.kelly import fractional_kelly_notional, full_kelly_fraction_binary


def test_full_kelly_binary():
    # p=0.6, c=0.5 -> f* = 0.1/0.5 = 0.2
    assert full_kelly_fraction_binary(model_prob=0.6, ask_price=0.5) == pytest.approx(0.2)
    assert full_kelly_fraction_binary(model_prob=0.5, ask_price=0.5) is None
    assert full_kelly_fraction_binary(model_prob=0.6, ask_price=0.0) is None


def test_fractional_kelly_notional():
    n = fractional_kelly_notional(
        bankroll_usd=1000.0,
        model_prob=0.6,
        ask_price=0.5,
        kelly_fraction=0.25,
        max_order_notional_usd=100.0,
    )
    # f* = 0.2, quarter Kelly => 0.05 * 1000 = 50
    assert n == pytest.approx(50.0)

    capped = fractional_kelly_notional(
        bankroll_usd=1_000_000.0,
        model_prob=0.6,
        ask_price=0.5,
        kelly_fraction=1.0,
        max_order_notional_usd=10.0,
    )
    assert capped == 10.0
