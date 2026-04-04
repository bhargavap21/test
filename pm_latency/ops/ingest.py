"""Run dual CEX + Polymarket CLOB ingestion (read-only)."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import sys
import time
from collections import deque
from pathlib import Path

from pm_latency.connectors.binance_ws import DEFAULT_BINANCE_WS
from pm_latency.connectors.cex_mux import run_cex_feed
from pm_latency.connectors.coinbase_ws import DEFAULT_COINBASE_WS
from pm_latency.connectors.polymarket_ws import DEFAULT_CLOB_MARKET_WS, run_polymarket_market_ws
from pm_latency.domain.cex_symbols import collect_token_ids_and_binance_symbols
from pm_latency.domain.registry import MarketRegistry
from pm_latency.domain.ticks import MarketTick


def _recv_delay_ms(tick: MarketTick) -> float | None:
    if tick.ts_exchange_ms is None:
        return None
    recv_wall_ns = time.time_ns()
    ex_ns = int(tick.ts_exchange_ms) * 1_000_000
    return (recv_wall_ns - ex_ns) / 1_000_000.0


class IngestStats:
    def __init__(self, max_samples: int = 2000) -> None:
        self.cex_ticks = 0
        self.pm_ticks = 0
        self.last_cex_recv_ns: int | None = None
        self.last_pm_recv_ns: int | None = None
        self._cex_delays: deque[float] = deque(maxlen=max_samples)
        self._pm_delays: deque[float] = deque(maxlen=max_samples)

    def record(self, tick: MarketTick) -> None:
        d = _recv_delay_ms(tick)
        if tick.source == "cex":
            self.cex_ticks += 1
            self.last_cex_recv_ns = tick.ts_recv_ns
            if d is not None:
                self._cex_delays.append(d)
        else:
            self.pm_ticks += 1
            self.last_pm_recv_ns = tick.ts_recv_ns
            if d is not None:
                self._pm_delays.append(d)

    def summary(self) -> dict:
        def _pct(q: deque[float], p: float) -> float | None:
            if not q:
                return None
            s = sorted(q)
            i = int(round((len(s) - 1) * p))
            return s[max(0, min(i, len(s) - 1))]

        now = time.monotonic_ns()
        return {
            "cex_ticks": self.cex_ticks,
            "pm_ticks": self.pm_ticks,
            "cex_age_ms": _age_ms(now, self.last_cex_recv_ns),
            "pm_age_ms": _age_ms(now, self.last_pm_recv_ns),
            "cex_delay_ms_p50": _pct(self._cex_delays, 0.50),
            "cex_delay_ms_p95": _pct(self._cex_delays, 0.95),
            "pm_delay_ms_p50": _pct(self._pm_delays, 0.50),
            "pm_delay_ms_p95": _pct(self._pm_delays, 0.95),
        }


def _age_ms(now_ns: int, last_ns: int | None) -> float | None:
    if last_ns is None:
        return None
    return (now_ns - last_ns) / 1_000_000.0


async def run_dual_ingest(
    *,
    registry_path: Path,
    include_closed: bool,
    enable_cex: bool,
    enable_polymarket: bool,
    cex_provider: str,
    binance_ws: str,
    coinbase_ws: str,
    polymarket_ws: str,
    duration_s: float,
    verbose: bool,
    log_interval_s: float = 5.0,
    stale_warn_ms: float = 10_000.0,
) -> None:
    reg = MarketRegistry(registry_path)
    rows = list(reg.iter_tradable() if not include_closed else reg.iter_all())
    if not rows:
        print(
            "ingest: no markets in registry; run `pm-runner discover` first.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    token_ids, symbols = collect_token_ids_and_binance_symbols(rows)
    if not token_ids:
        print("ingest: no clob token ids in registry rows.", file=sys.stderr)
        raise SystemExit(2)

    print(
        f"ingest: {len(rows)} market row(s), {len(token_ids)} token id(s), "
        f"cex={enable_cex} provider={cex_provider if enable_cex else 'off'} "
        f"binance_symbols={symbols if enable_cex else ()}, "
        f"polymarket={enable_polymarket}",
        file=sys.stderr,
    )

    if not enable_cex and not enable_polymarket:
        print("ingest: nothing to run (both CEX and Polymarket disabled).", file=sys.stderr)
        raise SystemExit(2)

    stop = asyncio.Event()
    stats = IngestStats()

    if duration_s > 0:

        async def _stop_later() -> None:
            await asyncio.sleep(duration_s)
            stop.set()

        asyncio.create_task(_stop_later())

    async def on_tick(tick: MarketTick) -> None:
        stats.record(tick)
        if verbose:
            line = {
                "source": tick.source,
                "venue": tick.venue,
                "symbol": tick.symbol,
                "ts_exchange_ms": tick.ts_exchange_ms,
                "delay_recv_minus_exchange_ms": _recv_delay_ms(tick),
                "best_bid": tick.best_bid,
                "best_ask": tick.best_ask,
                "mid": tick.mid,
                "event": tick.raw_event_type,
            }
            print(json.dumps(line, separators=(",", ":")))

    async def _reporter() -> None:
        while not stop.is_set():
            await asyncio.sleep(log_interval_s)
            if stop.is_set():
                break
            if not verbose:
                s = stats.summary()
                print(f"ingest: summary {json.dumps(s)}", file=sys.stderr)
                cex_age = s.get("cex_age_ms")
                pm_age = s.get("pm_age_ms")
                if cex_age is not None and cex_age > stale_warn_ms:
                    print(
                        f"ingest: WARN cex stale {cex_age:.0f}ms since last tick "
                        f"(threshold {stale_warn_ms:.0f}ms)",
                        file=sys.stderr,
                    )
                if pm_age is not None and pm_age > stale_warn_ms:
                    print(
                        f"ingest: WARN polymarket stale {pm_age:.0f}ms since last tick "
                        f"(threshold {stale_warn_ms:.0f}ms)",
                        file=sys.stderr,
                    )

    reporter = asyncio.create_task(_reporter())

    async def _guarded_cex() -> None:
        if not enable_cex:
            await stop.wait()
            return
        try:
            await run_cex_feed(
                provider=cex_provider,
                rows=rows,
                binance_ws=binance_ws,
                coinbase_ws=coinbase_ws,
                on_tick=on_tick,
                stop=stop,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"ingest: CEX connector exited ({type(e).__name__}: {e})", file=sys.stderr)

    async def _guarded_polymarket() -> None:
        if not enable_polymarket:
            await stop.wait()
            return
        try:
            await run_polymarket_market_ws(
                ws_url=polymarket_ws,
                token_ids=token_ids,
                on_tick=on_tick,
                stop=stop,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(
                f"ingest: Polymarket connector exited ({type(e).__name__}: {e})",
                file=sys.stderr,
            )

    try:
        await asyncio.gather(_guarded_cex(), _guarded_polymarket())
    finally:
        reporter.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reporter
        if not verbose:
            print(f"ingest: final {json.dumps(stats.summary())}", file=sys.stderr)


def main_ingest(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="pm-runner ingest",
        description="Read-only Binance bookTicker + Polymarket CLOB market WS for registry tokens.",
    )
    p.add_argument(
        "--registry",
        default=os.environ.get("PM_REGISTRY_PATH", "data/markets.db"),
        help="SQLite registry path.",
    )
    p.add_argument(
        "--include-closed",
        action="store_true",
        help="Subscribe to all rows in DB, not only accepting_orders & open.",
    )
    p.add_argument(
        "--no-cex",
        action="store_true",
        help="Skip Binance WebSocket (e.g. HTTP 451 in some regions).",
    )
    p.add_argument(
        "--no-polymarket",
        action="store_true",
        help="Skip Polymarket CLOB WebSocket (CEX-only debug).",
    )
    p.add_argument(
        "--cex",
        default=os.environ.get("CEX_PROVIDER", "auto"),
        choices=("auto", "binance", "coinbase"),
        help="CEX feed: auto tries Binance then Coinbase (e.g. after HTTP 451).",
    )
    p.add_argument(
        "--binance-ws",
        default=os.environ.get("BINANCE_WS_BASE", DEFAULT_BINANCE_WS),
        help="Binance combined stream base URL.",
    )
    p.add_argument(
        "--coinbase-ws",
        default=os.environ.get("COINBASE_WS_URL", DEFAULT_COINBASE_WS),
        help="Coinbase Exchange WebSocket URL.",
    )
    p.add_argument(
        "--polymarket-ws",
        default=os.environ.get("POLYMARKET_CLOB_WS", DEFAULT_CLOB_MARKET_WS),
        help="Polymarket CLOB market WebSocket URL.",
    )
    p.add_argument(
        "--duration",
        type=float,
        default=60.0,
        help="Seconds to run (0 = until Ctrl-C). Default 60.",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Print one JSON line per tick to stdout.",
    )
    p.add_argument(
        "--log-interval",
        type=float,
        default=5.0,
        help="Seconds between stderr summaries when not --verbose.",
    )
    p.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Less noise (only errors from libraries).",
    )
    p.add_argument(
        "--stale-warn-ms",
        type=float,
        default=10_000.0,
        help="Warn on stderr if no tick from venue within this many ms (monotonic clock).",
    )
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        asyncio.run(
            run_dual_ingest(
                registry_path=Path(args.registry),
                include_closed=args.include_closed,
                enable_cex=not args.no_cex,
                enable_polymarket=not args.no_polymarket,
                cex_provider=args.cex,
                binance_ws=args.binance_ws,
                coinbase_ws=args.coinbase_ws,
                polymarket_ws=args.polymarket_ws,
                duration_s=args.duration,
                verbose=args.verbose,
                log_interval_s=args.log_interval,
                stale_warn_ms=args.stale_warn_ms,
            )
        )
    except KeyboardInterrupt:
        return 130
    return 0
