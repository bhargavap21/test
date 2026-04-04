"""Run paper trading dashboard (FastAPI + uvicorn)."""

from __future__ import annotations

import argparse
import os
import sys


def main_dashboard(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="pm-runner dashboard",
        description="Web UI for paper ledger P&L (FastAPI).",
    )
    p.add_argument("--host", default=os.environ.get("DASHBOARD_HOST", "127.0.0.1"))
    p.add_argument("--port", type=int, default=int(os.environ.get("DASHBOARD_PORT", "8765")))
    p.add_argument(
        "--ledger",
        default=os.environ.get("PAPER_LEDGER_DB", "data/paper_ledger.db"),
        help="Same path as paper loop PAPER_LEDGER_DB.",
    )
    args = p.parse_args(argv)

    os.environ["PAPER_LEDGER_DB"] = args.ledger

    try:
        import uvicorn
    except ImportError:
        print(
            "dashboard: install optional deps: pip install 'pm-latency[dashboard]'",
            file=sys.stderr,
        )
        return 2

    uvicorn.run(
        "pm_latency.paperdash.app:app",
        host=args.host,
        port=args.port,
        log_level="info",
    )
    return 0
