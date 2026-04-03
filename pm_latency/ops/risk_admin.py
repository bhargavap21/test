"""Inspect risk limits, kill switch, and risk state file."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from pm_latency.risk.config import limits_from_environ
from pm_latency.risk.engine import OrderRequest, RiskEngine
from pm_latency.risk.kill_switch import default_kill_file, kill_switch_active
from pm_latency.risk.state import load_risk_state


def main_risk(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="pm-runner risk",
        description="Risk engine: status, kill switch, dry-run sizing.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    st = sub.add_parser("status", help="Print limits, kill state, and risk JSON state.")
    st.add_argument(
        "--state",
        default=os.environ.get("PM_RISK_STATE_PATH", "data/risk_state.json"),
    )
    st.add_argument(
        "--kill-file",
        default=os.environ.get("PM_KILL_FILE", str(default_kill_file())),
    )

    kill = sub.add_parser("kill", help="Create kill file (stops new orders).")
    kill.add_argument(
        "--kill-file",
        default=os.environ.get("PM_KILL_FILE", str(default_kill_file())),
    )

    unkill = sub.add_parser("unkill", help="Remove kill file.")
    unkill.add_argument(
        "--kill-file",
        default=os.environ.get("PM_KILL_FILE", str(default_kill_file())),
    )

    dry = sub.add_parser("dry-order", help="Evaluate one hypothetical buy vs limits.")
    dry.add_argument("--condition-id", required=True)
    dry.add_argument("--model-prob", type=float, required=True)
    dry.add_argument("--ask", type=float, required=True, dest="ask_price")
    dry.add_argument(
        "--state",
        default=os.environ.get("PM_RISK_STATE_PATH", "data/risk_state.json"),
    )
    dry.add_argument(
        "--kill-file",
        default=os.environ.get("PM_KILL_FILE", str(default_kill_file())),
    )

    args = p.parse_args(argv)

    if args.cmd == "status":
        lim = limits_from_environ()
        kpath = Path(args.kill_file)
        blocked = kill_switch_active(kill_file=kpath)
        state = load_risk_state(Path(args.state))
        state.reset_if_new_day()
        out = {
            "limits": {
                "bankroll_usd": lim.bankroll_usd,
                "max_total_exposure_usd": lim.max_total_exposure_usd,
                "max_market_exposure_usd": lim.max_market_exposure_usd,
                "max_order_notional_usd": lim.max_order_notional_usd,
                "daily_loss_limit_usd": lim.daily_loss_limit_usd,
                "kelly_fraction": lim.kelly_fraction,
                "max_orders_per_minute": lim.max_orders_per_minute,
            },
            "kill_file": str(kpath),
            "trading_blocked": blocked,
            "state": state.to_dict(),
        }
        print(json.dumps(out, indent=2))
        return 0

    if args.cmd == "kill":
        kpath = Path(args.kill_file)
        kpath.parent.mkdir(parents=True, exist_ok=True)
        kpath.write_text("1\n", encoding="utf-8")
        print(f"risk: wrote kill file {kpath}", file=sys.stderr)
        return 0

    if args.cmd == "unkill":
        kpath = Path(args.kill_file)
        kpath.unlink(missing_ok=True)
        print(f"risk: removed kill file {kpath}", file=sys.stderr)
        return 0

    if args.cmd == "dry-order":
        eng = RiskEngine(
            state_path=Path(args.state),
            kill_file=Path(args.kill_file),
        )
        req = OrderRequest(
            condition_id=args.condition_id,
            token_id="dry",
            outcome="Up",
            model_prob=args.model_prob,
            ask_price=args.ask_price,
        )
        d = eng.evaluate(req)
        print(
            json.dumps(
                {
                    "allowed": d.allowed,
                    "reason": d.reason,
                    "notional_usd": d.notional_usd,
                    "contracts": d.contracts,
                    "kelly_f_star": d.kelly_f_star,
                },
                indent=2,
            )
        )
        return 0

    return 2
