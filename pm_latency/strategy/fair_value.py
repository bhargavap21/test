"""Model probability for Up/Down window markets vs CLOB quotes."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from pm_latency.domain.models import TradedMarket
from pm_latency.strategy.resolution_contract import ResolutionContract, contract_from_traded_market
from pm_latency.strategy.volatility import EwmaVol

_SECONDS_PER_YEAR = 365.25 * 24 * 3600


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def prob_up_terminal(
    *,
    mid: float,
    anchor: float,
    tau_seconds: float,
    sigma_annual: float,
) -> float:
    """
    P(S_T >= anchor | S_now = mid) under GBM with zero drift (short-horizon proxy).

    log(S_T/S_now) ~ N(-0.5 sigma^2 tau, sigma^2 tau) in year fraction tau_years.
    """
    if mid <= 0 or anchor <= 0:
        return float("nan")
    if tau_seconds <= 0:
        return 1.0 if mid >= anchor else 0.0
    if sigma_annual <= 0:
        return 1.0 if mid >= anchor else 0.0

    tau_years = tau_seconds / _SECONDS_PER_YEAR
    vol = sigma_annual * math.sqrt(tau_years)
    if vol < 1e-12:
        return 1.0 if mid >= anchor else 0.0

    m = math.log(mid / anchor) - 0.5 * (sigma_annual**2) * tau_years
    return float(normal_cdf(m / vol))


@dataclass(frozen=True, slots=True)
class OutcomeQuote:
    outcome: str
    token_id: str
    best_bid: float | None
    best_ask: float | None


@dataclass(frozen=True, slots=True)
class EdgeEstimate:
    market: TradedMarket
    contract: ResolutionContract
    now_ts: float
    cex_mid: float
    anchor_mid: float | None
    sigma_annual: float
    tau_seconds: float
    p_up: float
    outcomes: tuple[str, ...]
    model_prob_by_outcome: dict[str, float]
    """Positive => model thinks outcome is underpriced at the ask (buy edge)."""
    edge_buy_vs_ask: dict[str, float | None]


def _now_ts() -> float:
    return time.time()


def _normalize_outcome(s: str) -> str:
    return s.strip().lower()


def build_outcome_quotes(
    market: TradedMarket,
    quotes_by_token: dict[str, tuple[float | None, float | None]],
) -> list[OutcomeQuote]:
    out: list[OutcomeQuote] = []
    for name, tid in zip(market.outcomes, market.token_ids, strict=True):
        bid, ask = quotes_by_token.get(str(tid), (None, None))
        out.append(OutcomeQuote(str(name), str(tid), bid, ask))
    return out


@dataclass
class WindowFairValueState:
    """Rolling CEX-based fair value for one TradedMarket window."""

    market: TradedMarket
    vol: EwmaVol
    anchor_mid: float | None = None

    @property
    def contract(self) -> ResolutionContract:
        return contract_from_traded_market(self.market)

    def on_cex_tick(self, mid: float, ts_ms: int | None) -> None:
        self.vol.update(mid, ts_ms)
        now = _now_ts()
        if self.anchor_mid is None and now >= self.contract.window_start_ts:
            self.anchor_mid = mid

    def snapshot(
        self,
        cex_mid: float,
        cex_ts_ms: int | None,
        quotes_by_token: dict[str, tuple[float | None, float | None]],
        *,
        sigma_floor: float = 0.01,
    ) -> EdgeEstimate | None:
        self.vol.update(cex_mid, cex_ts_ms)
        now = _now_ts()
        if self.anchor_mid is None and now >= self.contract.window_start_ts:
            self.anchor_mid = cex_mid

        anchor = self.anchor_mid
        if anchor is None or anchor <= 0:
            return None

        tau = self.contract.window_end_ts - now
        sigma = self.vol.sigma_annual()
        if sigma <= 0:
            sigma = max(sigma_floor, 1e-6)

        p_up = prob_up_terminal(
            mid=cex_mid,
            anchor=anchor,
            tau_seconds=max(tau, 0.0),
            sigma_annual=sigma,
        )

        probs: dict[str, float] = {}
        for o in self.market.outcomes:
            key = _normalize_outcome(str(o))
            if key == "up":
                probs[str(o)] = p_up
            elif key == "down":
                probs[str(o)] = 1.0 - p_up
            else:
                probs[str(o)] = float("nan")

        edge_buy: dict[str, float | None] = {}
        oquotes = build_outcome_quotes(self.market, quotes_by_token)
        for q in oquotes:
            p = probs.get(q.outcome, float("nan"))
            if q.best_ask is None or math.isnan(p):
                edge_buy[q.outcome] = None
            else:
                edge_buy[q.outcome] = float(p - q.best_ask)

        c = self.contract
        return EdgeEstimate(
            market=self.market,
            contract=c,
            now_ts=now,
            cex_mid=cex_mid,
            anchor_mid=anchor,
            sigma_annual=sigma,
            tau_seconds=max(tau, 0.0),
            p_up=p_up,
            outcomes=self.market.outcomes,
            model_prob_by_outcome=probs,
            edge_buy_vs_ask=edge_buy,
        )
