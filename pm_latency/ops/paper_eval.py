"""Pure helpers for paper-trading intent generation (testable without I/O)."""

from __future__ import annotations

import hashlib
import math
import time
import uuid
from dataclasses import dataclass

from pm_latency.risk.engine import OrderRequest, RiskDecision, RiskEngine
from pm_latency.strategy.fair_value import EdgeEstimate, build_outcome_quotes


@dataclass(frozen=True, slots=True)
class PaperCandidate:
    """Pre-risk edge candidate (sequential RiskEngine.evaluate in the runner)."""

    intent_key: str
    ts_unix: float
    condition_id: str
    event_slug: str
    outcome: str
    token_id: str
    model_prob: float
    ask_price: float
    edge_buy_vs_ask: float
    order_type: str


@dataclass(frozen=True, slots=True)
class PaperIntent:
    """One hypothetical buy at best ask after risk gate."""

    intent_id: str
    intent_key: str
    ts_unix: float
    mode: str  # "paper"
    condition_id: str
    event_slug: str
    outcome: str
    token_id: str
    model_prob: float
    ask_price: float
    edge_buy_vs_ask: float
    risk: RiskDecision
    order_type: str  # "FAK" | "GTC" for future execution


def stable_intent_key(
    *,
    condition_id: str,
    token_id: str,
    outcome: str,
    ask_price: float,
    model_prob: float,
) -> str:
    payload = f"{condition_id}|{token_id}|{outcome}|{ask_price:.6f}|{model_prob:.6f}"
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def candidates_from_snapshot_and_quotes(
    snap: EdgeEstimate,
    quotes_by_token: dict[str, tuple[float | None, float | None]],
    *,
    min_edge: float,
    order_type: str = "FAK",
) -> list[PaperCandidate]:
    """Outcomes with edge >= min_edge (risk applied separately for correct rate limits)."""
    out: list[PaperCandidate] = []
    now = time.time()
    for q in build_outcome_quotes(snap.market, quotes_by_token):
        if q.best_ask is None:
            continue
        ask = float(q.best_ask)
        if not (0.0 < ask < 1.0):
            continue
        p = snap.model_prob_by_outcome.get(q.outcome)
        if p is None or math.isnan(p):
            continue
        edge = float(p) - ask
        if edge < min_edge:
            continue

        ikey = stable_intent_key(
            condition_id=snap.market.condition_id,
            token_id=q.token_id,
            outcome=q.outcome,
            ask_price=ask,
            model_prob=float(p),
        )
        out.append(
            PaperCandidate(
                intent_key=ikey,
                ts_unix=now,
                condition_id=snap.market.condition_id,
                event_slug=snap.market.event_slug,
                outcome=q.outcome,
                token_id=q.token_id,
                model_prob=float(p),
                ask_price=ask,
                edge_buy_vs_ask=edge,
                order_type=order_type,
            )
        )
    return out


def finalize_candidates_with_risk(
    risk: RiskEngine,
    candidates: list[PaperCandidate],
    *,
    record_rate_on_allow: bool = True,
) -> list[PaperIntent]:
    """Run RiskEngine.evaluate in order; optionally record rate-limit timestamps when allowed."""
    out: list[PaperIntent] = []
    for c in candidates:
        req = OrderRequest(
            condition_id=c.condition_id,
            token_id=c.token_id,
            outcome=c.outcome,
            model_prob=c.model_prob,
            ask_price=c.ask_price,
        )
        dec = risk.evaluate(req)
        if dec.allowed and record_rate_on_allow:
            risk.record_order_sent()
        out.append(
            PaperIntent(
                intent_id=str(uuid.uuid4()),
                intent_key=c.intent_key,
                ts_unix=c.ts_unix,
                mode="paper",
                condition_id=c.condition_id,
                event_slug=c.event_slug,
                outcome=c.outcome,
                token_id=c.token_id,
                model_prob=c.model_prob,
                ask_price=c.ask_price,
                edge_buy_vs_ask=c.edge_buy_vs_ask,
                risk=dec,
                order_type=c.order_type,
            )
        )
    return out


def intent_to_jsonable(intent: PaperIntent) -> dict:
    return {
        "intent_id": intent.intent_id,
        "intent_key": intent.intent_key,
        "ts_unix": intent.ts_unix,
        "mode": intent.mode,
        "condition_id": intent.condition_id,
        "event_slug": intent.event_slug,
        "outcome": intent.outcome,
        "token_id": intent.token_id,
        "model_prob": intent.model_prob,
        "ask_price": intent.ask_price,
        "edge_buy_vs_ask": intent.edge_buy_vs_ask,
        "order_type": intent.order_type,
        "risk_allowed": intent.risk.allowed,
        "risk_reason": intent.risk.reason,
        "notional_usd": intent.risk.notional_usd,
        "contracts": intent.risk.contracts,
        "kelly_f_star": intent.risk.kelly_f_star,
    }
