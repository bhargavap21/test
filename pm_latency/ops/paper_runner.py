"""Paper trading: live feeds → fair value → risk → JSON intents (no CLOB orders)."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

from pm_latency.connectors.binance_ws import DEFAULT_BINANCE_WS
from pm_latency.connectors.cex_mux import run_cex_feed
from pm_latency.connectors.coinbase_ws import DEFAULT_COINBASE_WS
from pm_latency.connectors.polymarket_ws import DEFAULT_CLOB_MARKET_WS, run_polymarket_market_ws
from pm_latency.domain.cex_symbols import collect_token_ids_and_binance_symbols
from pm_latency.domain.registry import MarketRegistry
from pm_latency.domain.ticks import MarketTick
from pm_latency.ops.paper_eval import (
    candidates_from_snapshot_and_quotes,
    finalize_candidates_with_risk,
    intent_to_jsonable,
)
from pm_latency.paperdash.ledger import PaperLedger
from pm_latency.risk.engine import RiskEngine
from pm_latency.strategy.fair_value import WindowFairValueState
from pm_latency.strategy.volatility import EwmaVol

logger = logging.getLogger(__name__)


def _symbol_to_asset(sym: str) -> str | None:
    s = sym.upper().strip().replace("-", "")
    if s in ("BTCUSDT", "BTCUSD"):
        return "btc"
    if s in ("ETHUSDT", "ETHUSD"):
        return "eth"
    return None


async def run_paper(
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
    min_edge: float,
    sigma_floor: float,
    eval_interval_s: float,
    dedupe_ttl_s: float,
    order_type: str,
    risk_state_path: Path,
    kill_file: Path,
    log_file: Path | None,
    also_stderr: bool,
    ledger: PaperLedger | None,
    simulate_orders: bool,
) -> None:
    reg = MarketRegistry(registry_path)
    rows = list(reg.iter_tradable() if not include_closed else reg.iter_all())
    if not rows:
        print("paper: no markets in registry; run `pm-runner discover` first.", file=sys.stderr)
        raise SystemExit(2)

    token_ids, _binance_syms = collect_token_ids_and_binance_symbols(rows)
    if not token_ids:
        print("paper: no token ids in registry.", file=sys.stderr)
        raise SystemExit(2)

    fv_states: dict[str, WindowFairValueState] = {}
    for r in rows:
        fv_states[r.condition_id] = WindowFairValueState(
            market=r,
            vol=EwmaVol(min_updates=1, half_life_seconds=300.0),
        )

    quotes_by_token: dict[str, tuple[float | None, float | None]] = {}
    last_cex: dict[str, tuple[float, int | None]] = {}  # asset -> (mid, ts_ms)

    risk = RiskEngine(state_path=risk_state_path, kill_file=kill_file)
    lock = asyncio.Lock()
    stop = asyncio.Event()
    last_eval_mono = 0.0
    dedupe: dict[str, float] = {}  # intent_key -> last emit mono

    log_fp = log_file.open("a", encoding="utf-8") if log_file else None

    def _emit_intents(intents: list) -> None:
        nonlocal dedupe
        now_m = time.monotonic()
        for it in intents:
            key = it.intent_key
            prev = dedupe.get(key)
            if prev is not None and (now_m - prev) < dedupe_ttl_s:
                continue
            dedupe = {k: v for k, v in dedupe.items() if now_m - v < dedupe_ttl_s * 4}
            dedupe[key] = now_m
            line = json.dumps(intent_to_jsonable(it), separators=(",", ":"))
            print(line, flush=True)
            if log_fp:
                log_fp.write(line + "\n")
                log_fp.flush()
            if also_stderr:
                print(line, file=sys.stderr, flush=True)
            if ledger is not None and simulate_orders and it.risk.allowed and it.risk.contracts > 0:
                d = json.loads(line)
                ledger.record_simulated_buy(
                    condition_id=it.condition_id,
                    event_slug=it.event_slug,
                    outcome=it.outcome,
                    token_id=it.token_id,
                    contracts=float(it.risk.contracts),
                    entry_price=float(it.ask_price),
                    intent_id=str(d["intent_id"]),
                    intent_key=str(d["intent_key"]),
                )

    async def maybe_evaluate() -> None:
        nonlocal last_eval_mono
        async with lock:
            now_m = time.monotonic()
            if now_m - last_eval_mono < eval_interval_s:
                return
            last_eval_mono = now_m
            risk.reload_state()

            batch: list = []
            for st in fv_states.values():
                asset = st.market.asset
                if asset not in last_cex:
                    continue
                mid, ts_ms = last_cex[asset]
                snap = st.snapshot(mid, ts_ms, quotes_by_token, sigma_floor=sigma_floor)
                if snap is None:
                    continue
                batch.extend(
                    candidates_from_snapshot_and_quotes(
                        snap,
                        quotes_by_token,
                        min_edge=min_edge,
                        order_type=order_type,
                    )
                )
        if batch:
            intents = finalize_candidates_with_risk(
                risk,
                batch,
                record_rate_on_allow=False,
            )
            _emit_intents(intents)

    async def on_tick(tick: MarketTick) -> None:
        snap: dict[str, tuple[float | None, float | None]] | None = None
        async with lock:
            if (
                tick.source == "polymarket"
                and tick.best_bid is not None
                and tick.best_ask is not None
            ):
                quotes_by_token[tick.symbol] = (tick.best_bid, tick.best_ask)
                if ledger is not None:
                    snap = dict(quotes_by_token)
            elif tick.source == "cex" and tick.mid is not None:
                asset = _symbol_to_asset(tick.symbol)
                if asset:
                    last_cex[asset] = (float(tick.mid), tick.ts_exchange_ms)
                    for st in fv_states.values():
                        if st.market.asset == asset:
                            st.on_cex_tick(float(tick.mid), tick.ts_exchange_ms)
        if ledger is not None and snap:
            ledger.update_quotes(snap)
        await maybe_evaluate()

    if duration_s > 0:

        async def _stop_later() -> None:
            await asyncio.sleep(duration_s)
            stop.set()

        asyncio.create_task(_stop_later())

    print(
        f"paper: markets={len(rows)} tokens={len(token_ids)} "
        f"cex={enable_cex} cex_provider={cex_provider if enable_cex else 'off'} "
        f"pm={enable_polymarket} min_edge={min_edge} "
        f"ledger={ledger.path if ledger else 'off'} simulate={simulate_orders}",
        file=sys.stderr,
    )
    if not enable_cex:
        print(
            "paper: WARNING without CEX there is no spot for the model; "
            "use another feed or run with CEX enabled.",
            file=sys.stderr,
        )

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
            print(f"paper: CEX exited ({type(e).__name__}: {e})", file=sys.stderr)

    async def _guarded_pm() -> None:
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
            print(f"paper: Polymarket exited ({type(e).__name__}: {e})", file=sys.stderr)

    try:
        await asyncio.gather(_guarded_cex(), _guarded_pm())
    finally:
        if log_fp:
            log_fp.close()


def main_paper(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="pm-runner paper",
        description="Paper loop: WS feeds → model → risk → JSON intents (stdout). No orders.",
    )
    p.add_argument(
        "--registry",
        default=os.environ.get("PM_REGISTRY_PATH", "data/markets.db"),
    )
    p.add_argument("--include-closed", action="store_true")
    p.add_argument("--no-cex", action="store_true")
    p.add_argument("--no-polymarket", action="store_true")
    p.add_argument(
        "--cex",
        default=os.environ.get("CEX_PROVIDER", "auto"),
        choices=("auto", "binance", "coinbase"),
        help="CEX: auto = Binance then Coinbase if Binance fails (e.g. HTTP 451).",
    )
    p.add_argument(
        "--binance-ws",
        default=os.environ.get("BINANCE_WS_BASE", DEFAULT_BINANCE_WS),
    )
    p.add_argument(
        "--coinbase-ws",
        default=os.environ.get("COINBASE_WS_URL", DEFAULT_COINBASE_WS),
    )
    p.add_argument(
        "--polymarket-ws",
        default=os.environ.get("POLYMARKET_CLOB_WS", DEFAULT_CLOB_MARKET_WS),
    )
    p.add_argument("--duration", type=float, default=0.0, help="0 = run until Ctrl-C")
    p.add_argument(
        "--min-edge",
        type=float,
        default=float(os.environ.get("STRATEGY_MIN_EDGE", "0.02")),
        help="Minimum model_prob - ask to consider (default STRATEGY_MIN_EDGE or 0.02).",
    )
    p.add_argument(
        "--sigma-floor",
        type=float,
        default=float(os.environ.get("STRATEGY_SIGMA_FLOOR", "0.01")),
    )
    p.add_argument(
        "--eval-interval",
        type=float,
        default=float(os.environ.get("PAPER_EVAL_INTERVAL_S", "0.5")),
        help="Seconds between evaluation passes (default 0.5).",
    )
    p.add_argument(
        "--dedupe-ttl",
        type=float,
        default=30.0,
        help="Suppress duplicate intent_key emissions within this many seconds.",
    )
    p.add_argument(
        "--order-type",
        default=os.environ.get("PAPER_ORDER_TYPE", "FAK"),
        choices=("FAK", "GTC"),
    )
    p.add_argument(
        "--risk-state",
        default=os.environ.get("PM_RISK_STATE_PATH", "data/risk_state.json"),
    )
    p.add_argument(
        "--kill-file",
        default=os.environ.get("PM_KILL_FILE", str(Path("data/kill"))),
    )
    p.add_argument(
        "--log-file",
        default="",
        help="Append JSON lines here in addition to stdout.",
    )
    p.add_argument(
        "--also-stderr",
        action="store_true",
        help="Mirror each intent line to stderr.",
    )
    p.add_argument(
        "--ledger-db",
        default=os.environ.get("PAPER_LEDGER_DB", "data/paper_ledger.db"),
        help="SQLite path for simulated fills + dashboard.",
    )
    p.add_argument(
        "--no-ledger",
        action="store_true",
        help="Disable simulated fills (intents / JSONL only).",
    )
    p.add_argument(
        "--no-simulate",
        action="store_true",
        help="Log intents only; do not write simulated fills to ledger.",
    )
    p.add_argument(
        "--taker-fee-bps",
        type=float,
        default=float(os.environ.get("PAPER_TAKER_FEE_BPS", "0")),
        help="Assumed taker fee on entry notional (basis points).",
    )
    p.add_argument(
        "--redeem-fee-bps",
        type=float,
        default=float(os.environ.get("PAPER_REDEEM_FEE_BPS", "0")),
        help="Assumed fee on winning payout at settlement (basis points).",
    )
    p.add_argument("-q", "--quiet", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    lf = Path(args.log_file) if args.log_file.strip() else None
    ldb = args.ledger_db.strip()
    led: PaperLedger | None = None
    if not args.no_ledger and ldb:
        led = PaperLedger(
            Path(ldb),
            taker_fee_bps=args.taker_fee_bps,
            redeem_fee_bps=args.redeem_fee_bps,
        )

    try:
        asyncio.run(
            run_paper(
                registry_path=Path(args.registry),
                include_closed=args.include_closed,
                enable_cex=not args.no_cex,
                enable_polymarket=not args.no_polymarket,
                cex_provider=args.cex,
                binance_ws=args.binance_ws,
                coinbase_ws=args.coinbase_ws,
                polymarket_ws=args.polymarket_ws,
                duration_s=args.duration,
                min_edge=args.min_edge,
                sigma_floor=args.sigma_floor,
                eval_interval_s=args.eval_interval,
                dedupe_ttl_s=args.dedupe_ttl,
                order_type=args.order_type,
                risk_state_path=Path(args.risk_state),
                kill_file=Path(args.kill_file),
                log_file=lf,
                also_stderr=args.also_stderr,
                ledger=led,
                simulate_orders=not args.no_simulate,
            )
        )
    except KeyboardInterrupt:
        return 130
    return 0
