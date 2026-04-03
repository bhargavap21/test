"""CLI entrypoint; wires the live loop in later phases."""

from __future__ import annotations

import argparse
import os
import sys


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def _env_dry_run() -> bool:
    raw = os.environ.get("DRY_RUN", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()

    parser = argparse.ArgumentParser(
        prog="pm-runner",
        description="Polymarket short-horizon bot. Phase 1: skeleton only.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Force paper mode (no orders).",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="Allow live mode when execution is implemented (DRY_RUN=0).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="pm-latency 0.1.0",
    )

    args = parser.parse_args(argv)

    if args.live:
        dry_run = False
    elif args.dry_run:
        dry_run = True
    else:
        dry_run = _env_dry_run()

    print(f"pm-latency: dry_run={dry_run} (stub; no market loop yet)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
