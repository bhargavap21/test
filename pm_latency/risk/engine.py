"""Single gate for order sizing and limit checks."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from pm_latency.risk.config import RiskLimits, limits_from_environ
from pm_latency.risk.kelly import fractional_kelly_notional, full_kelly_fraction_binary
from pm_latency.risk.kill_switch import default_kill_file, kill_switch_active
from pm_latency.risk.state import (
    RiskState,
    load_risk_state,
    now_unix,
    prune_order_times,
    save_risk_state,
)


@dataclass(frozen=True, slots=True)
class OrderRequest:
    condition_id: str
    token_id: str
    outcome: str
    model_prob: float
    ask_price: float


@dataclass(frozen=True, slots=True)
class RiskDecision:
    allowed: bool
    reason: str
    notional_usd: float
    contracts: float
    kelly_f_star: float | None


class RiskEngine:
    def __init__(
        self,
        limits: RiskLimits | None = None,
        *,
        state_path: Path | None = None,
        kill_file: Path | None = None,
    ) -> None:
        self.limits = limits or limits_from_environ()
        self.state_path = state_path or Path(
            os.environ.get("PM_RISK_STATE_PATH", "data/risk_state.json")
        )
        self.kill_file = kill_file if kill_file is not None else default_kill_file()
        self._state = load_risk_state(self.state_path)

    @property
    def state(self) -> RiskState:
        return self._state

    def reload_state(self) -> None:
        self._state = load_risk_state(self.state_path)
        self._state.reset_if_new_day()

    def is_killed(self) -> bool:
        return kill_switch_active(kill_file=self.kill_file)

    def evaluate(self, req: OrderRequest) -> RiskDecision:
        self._state.reset_if_new_day()

        if self.is_killed():
            return RiskDecision(False, "kill_switch", 0.0, 0.0, None)

        if self._state.daily_realized_pnl_usd <= -self.limits.daily_loss_limit_usd:
            return RiskDecision(
                False,
                "daily_loss_limit",
                0.0,
                0.0,
                None,
            )

        now = now_unix()
        recent = prune_order_times(self._state.order_timestamps_unix, now=now, window_s=60.0)
        self._state.order_timestamps_unix = recent
        if len(recent) >= self.limits.max_orders_per_minute:
            return RiskDecision(False, "rate_limit_orders_per_minute", 0.0, 0.0, None)

        f_star = full_kelly_fraction_binary(model_prob=req.model_prob, ask_price=req.ask_price)
        if f_star is None:
            return RiskDecision(False, "no_edge_or_invalid_prices", 0.0, 0.0, None)

        notion = fractional_kelly_notional(
            bankroll_usd=self.limits.bankroll_usd,
            model_prob=req.model_prob,
            ask_price=req.ask_price,
            kelly_fraction=self.limits.kelly_fraction,
            max_order_notional_usd=self.limits.max_order_notional_usd,
        )
        if notion <= 0:
            return RiskDecision(False, "zero_size", 0.0, 0.0, f_star)

        cur_m = self._state.exposure_usd_by_condition.get(req.condition_id, 0.0)
        total = sum(self._state.exposure_usd_by_condition.values())
        if cur_m + notion > self.limits.max_market_exposure_usd + 1e-9:
            return RiskDecision(False, "max_market_exposure", 0.0, 0.0, f_star)
        if total + notion > self.limits.max_total_exposure_usd + 1e-9:
            return RiskDecision(False, "max_total_exposure", 0.0, 0.0, f_star)

        contracts = notion / req.ask_price if req.ask_price > 0 else 0.0
        return RiskDecision(True, "ok", notion, contracts, f_star)

    def record_order_sent(self) -> None:
        """Call after placing an order to update rate limiter (and optionally persist)."""
        self._state.reset_if_new_day()
        self._state.order_timestamps_unix.append(now_unix())
        save_risk_state(self.state_path, self._state)

    def record_fill_notional(self, condition_id: str, notional_usd: float) -> None:
        """Increase exposure for a condition after a buy fill."""
        self._state.reset_if_new_day()
        cur = self._state.exposure_usd_by_condition.get(condition_id, 0.0)
        self._state.exposure_usd_by_condition[condition_id] = cur + notional_usd
        save_risk_state(self.state_path, self._state)

    def record_realized_pnl(self, delta_usd: float) -> None:
        """Update daily PnL (negative when losing)."""
        self._state.reset_if_new_day()
        self._state.daily_realized_pnl_usd += delta_usd
        save_risk_state(self.state_path, self._state)
