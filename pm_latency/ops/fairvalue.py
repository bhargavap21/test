"""Print resolution-aware model probs vs optional CLOB quotes (no orders)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from pm_latency.domain.registry import MarketRegistry
from pm_latency.strategy.fair_value import WindowFairValueState
from pm_latency.strategy.volatility import EwmaVol


def main_fairvalue(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="pm-runner fairvalue",
        description="GBM proxy fair value for Up/Down windows; CEX is a fast oracle proxy.",
    )
    p.add_argument(
        "--registry",
        default=os.environ.get("PM_REGISTRY_PATH", "data/markets.db"),
        help="SQLite registry path.",
    )
    p.add_argument(
        "--condition-id",
        default="",
        help="Single market condition_id; default = all tradable rows.",
    )
    p.add_argument(
        "--cex-mid",
        type=float,
        required=True,
        help="Spot mid from your CEX feed (proxy for resolution oracle).",
    )
    p.add_argument(
        "--cex-ts-ms",
        type=int,
        default=None,
        help="Optional exchange timestamp ms for vol update.",
    )
    p.add_argument(
        "--sigma-floor",
        type=float,
        default=0.01,
        help="Minimum annualized sigma when EWMA is not warmed up (default 0.01).",
    )
    p.add_argument(
        "--quotes-json",
        default="",
        help='Optional JSON: {"<token_id>": {"bid":0.4,"ask":0.42}, ...}',
    )
    args = p.parse_args(argv)

    reg = MarketRegistry(Path(args.registry))
    rows = list(reg.iter_tradable())
    if args.condition_id:
        rows = [r for r in rows if r.condition_id == args.condition_id]
    if not rows:
        print("fairvalue: no matching tradable markets.", file=sys.stderr)
        return 2

    quotes_by_token: dict[str, tuple[float | None, float | None]] = {}
    if args.quotes_json:
        raw = json.loads(args.quotes_json)
        if not isinstance(raw, dict):
            print("fairvalue: quotes-json must be an object.", file=sys.stderr)
            return 2
        for tid, v in raw.items():
            if isinstance(v, dict):
                quotes_by_token[str(tid)] = (
                    float(v["bid"]) if v.get("bid") is not None else None,
                    float(v["ask"]) if v.get("ask") is not None else None,
                )

    for m in rows:
        vol = EwmaVol(min_updates=1, half_life_seconds=300.0)
        st = WindowFairValueState(market=m, vol=vol)
        st.on_cex_tick(args.cex_mid, args.cex_ts_ms)
        snap = st.snapshot(
            args.cex_mid,
            args.cex_ts_ms,
            quotes_by_token,
            sigma_floor=args.sigma_floor,
        )
        if snap is None:
            c = st.contract
            out = {
                "condition_id": m.condition_id,
                "event_slug": m.event_slug,
                "note": "anchor not set (before window start or no tick through start)",
                "oracle_pair": c.oracle_pair,
                "window": [c.window_start_ts, c.window_end_ts],
            }
            print(json.dumps(out, separators=(",", ":")))
            continue

        out = {
            "condition_id": m.condition_id,
            "event_slug": m.event_slug,
            "oracle_pair": snap.contract.oracle_pair,
            "window": [snap.contract.window_start_ts, snap.contract.window_end_ts],
            "resolution_hint": snap.contract.resolution_hint,
            "cex_mid": snap.cex_mid,
            "anchor_mid": snap.anchor_mid,
            "tau_seconds": snap.tau_seconds,
            "sigma_annual": snap.sigma_annual,
            "p_up": snap.p_up,
            "model_prob_by_outcome": snap.model_prob_by_outcome,
            "edge_buy_vs_ask": snap.edge_buy_vs_ask,
        }
        print(json.dumps(out, separators=(",", ":")))

    return 0
