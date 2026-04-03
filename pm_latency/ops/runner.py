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

    av = list(sys.argv[1:] if argv is None else argv)

    if av and av[0] == "ingest":
        from pm_latency.ops.ingest import main_ingest

        return main_ingest(av[1:])

    if av and av[0] == "discover":
        dparser = argparse.ArgumentParser(
            prog="pm-runner discover",
            description="Probe Gamma for short BTC/ETH Up/Down windows and upsert SQLite registry.",
        )
        dparser.add_argument(
            "--registry",
            default=os.environ.get("PM_REGISTRY_PATH", "data/markets.db"),
            help="SQLite path (default: data/markets.db or PM_REGISTRY_PATH).",
        )
        dparser.add_argument(
            "--gamma-base",
            default=os.environ.get("GAMMA_API_BASE", "https://gamma-api.polymarket.com"),
            help="Gamma API origin (default: env GAMMA_API_BASE or production URL).",
        )
        args = dparser.parse_args(av[1:])

        from pathlib import Path

        from pm_latency.domain.registry import MarketRegistry
        from pm_latency.ops.discover import refresh_registry

        path = Path(args.registry)
        reg = MarketRegistry(path)
        n = refresh_registry(reg, gamma_base=args.gamma_base)
        print(f"discover: upserted {n} market row(s) into {path}", file=sys.stderr)
        return 0

    parser = argparse.ArgumentParser(
        prog="pm-runner",
        description="Polymarket short-horizon bot (incremental build).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="pm-latency 0.3.0",
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

    args = parser.parse_args(av)

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
