"""SQLite ledger for simulated paper fills, MTM, and settlement P&L."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_ts REAL NOT NULL,
    condition_id TEXT NOT NULL,
    event_slug TEXT,
    outcome TEXT NOT NULL,
    token_id TEXT NOT NULL,
    contracts REAL NOT NULL,
    entry_price REAL NOT NULL,
    notional_gross REAL NOT NULL,
    fee_entry_usd REAL NOT NULL DEFAULT 0,
    fee_exit_usd REAL NOT NULL DEFAULT 0,
    intent_id TEXT,
    intent_key TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    settled_ts REAL,
    winning_outcome TEXT,
    payout_usd REAL,
    realized_pnl_usd REAL
);
CREATE INDEX IF NOT EXISTS idx_fills_condition ON paper_fills(condition_id);
CREATE INDEX IF NOT EXISTS idx_fills_status ON paper_fills(status);
CREATE TABLE IF NOT EXISTS paper_quotes (
    token_id TEXT PRIMARY KEY,
    bid REAL,
    ask REAL,
    mid REAL,
    updated_ts REAL NOT NULL
);
"""


def _fee_usd(notional: float, fee_bps: float) -> float:
    return notional * (fee_bps / 10_000.0)


@dataclass
class PaperLedger:
    path: Path
    taker_fee_bps: float = 0.0
    redeem_fee_bps: float = 0.0

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.executescript(SCHEMA)
            conn.execute(
                "UPDATE paper_fills SET condition_id = lower(trim(condition_id)) "
                "WHERE condition_id != lower(trim(condition_id))"
            )
            conn.commit()

    def record_simulated_buy(
        self,
        *,
        condition_id: str,
        event_slug: str,
        outcome: str,
        token_id: str,
        contracts: float,
        entry_price: float,
        intent_id: str,
        intent_key: str,
    ) -> int:
        if contracts <= 0 or entry_price <= 0:
            return -1
        cid_norm = str(condition_id).strip().lower()
        notional = contracts * entry_price
        fee_in = _fee_usd(notional, self.taker_fee_bps)
        ts = time.time()
        with sqlite3.connect(self.path) as conn:
            cur = conn.execute(
                """
                INSERT INTO paper_fills (
                    created_ts, condition_id, event_slug, outcome, token_id,
                    contracts, entry_price, notional_gross, fee_entry_usd,
                    intent_id, intent_key, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
                """,
                (
                    ts,
                    cid_norm,
                    event_slug,
                    outcome,
                    token_id,
                    contracts,
                    entry_price,
                    notional,
                    fee_in,
                    intent_id,
                    intent_key,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def update_quotes(self, quotes: dict[str, tuple[float | None, float | None]]) -> None:
        ts = time.time()
        rows: list[tuple] = []
        for tid, (bid, ask) in quotes.items():
            if bid is None or ask is None:
                continue
            mid = (float(bid) + float(ask)) / 2.0
            rows.append((str(tid), float(bid), float(ask), mid, ts))
        if not rows:
            return
        with sqlite3.connect(self.path) as conn:
            conn.executemany(
                """
                INSERT INTO paper_quotes (token_id, bid, ask, mid, updated_ts)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(token_id) DO UPDATE SET
                    bid=excluded.bid, ask=excluded.ask, mid=excluded.mid,
                    updated_ts=excluded.updated_ts
                """,
                rows,
            )
            conn.commit()

    def open_fills(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM paper_fills WHERE status = 'open' ORDER BY id"
            )
            return [dict(r) for r in cur.fetchall()]

    def distinct_open_condition_ids(self) -> list[str]:
        with sqlite3.connect(self.path) as conn:
            cur = conn.execute(
                "SELECT DISTINCT condition_id FROM paper_fills WHERE status = 'open'"
            )
            return [str(r[0]) for r in cur.fetchall()]

    def settle_from_gamma_market(self, market: dict[str, Any]) -> int:
        """Settle open fills for this condition_id using Gamma market JSON. Returns rows updated."""
        cid = str(market.get("conditionId") or "").strip().lower()
        if not cid:
            return 0
        closed = bool(market.get("closed"))
        if not closed:
            return 0

        outcomes_raw = market.get("outcomes")
        prices_raw = market.get("outcomePrices")
        try:
            outs = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else outcomes_raw
            prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
        except (json.JSONDecodeError, TypeError):
            return 0
        if not isinstance(outs, list) or not isinstance(prices, list):
            return 0
        if len(outs) != len(prices) or not outs:
            return 0

        parsed: list[tuple[str, float]] = []
        for o, p in zip(outs, prices, strict=True):
            try:
                parsed.append((str(o).strip(), float(str(p).strip())))
            except ValueError:
                return 0

        winning: str | None = None
        for o, p in parsed:
            if p >= 0.99:
                winning = o
                break
        if winning is None:
            uma_ok = str(market.get("umaResolutionStatus") or "").lower() == "resolved"
            if not uma_ok:
                return 0
            sorted_p = sorted((p for _, p in parsed), reverse=True)
            top, second = sorted_p[0], sorted_p[1] if len(sorted_p) > 1 else 0.0
            if top <= 0.5 or (top - second) < 0.4:
                return 0
            best_i = max(range(len(parsed)), key=lambda i: parsed[i][1])
            winning = parsed[best_i][0]

        fills = self.open_fills()
        to_settle = [f for f in fills if str(f["condition_id"]).strip().lower() == cid]
        if not to_settle:
            return 0

        ts = time.time()
        n = 0
        with sqlite3.connect(self.path) as conn:
            for f in to_settle:
                contracts = float(f["contracts"])
                won = str(f["outcome"]).strip().casefold() == winning.casefold()
                payout = contracts * 1.0 if won else 0.0
                fee_out = _fee_usd(payout, self.redeem_fee_bps) if won else 0.0
                cost = float(f["notional_gross"]) + float(f["fee_entry_usd"])
                realized = payout - fee_out - cost
                conn.execute(
                    """
                    UPDATE paper_fills SET
                        status = 'settled',
                        settled_ts = ?,
                        winning_outcome = ?,
                        payout_usd = ?,
                        fee_exit_usd = ?,
                        realized_pnl_usd = ?
                    WHERE id = ?
                    """,
                    (ts, winning, payout, fee_out, realized, f["id"]),
                )
                n += 1
            conn.commit()
        return n

    def summary(self) -> dict[str, Any]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            open_rows = conn.execute(
                "SELECT COUNT(*) c, COALESCE(SUM(notional_gross + fee_entry_usd),0) cost "
                "FROM paper_fills WHERE status = 'open'"
            ).fetchone()
            settled = conn.execute(
                "SELECT COUNT(*) c, COALESCE(SUM(realized_pnl_usd),0) pnl, "
                "COALESCE(SUM(fee_entry_usd + fee_exit_usd),0) fees "
                "FROM paper_fills WHERE status = 'settled'"
            ).fetchone()

            unreal = 0.0
            for row in conn.execute("SELECT * FROM paper_fills WHERE status = 'open'"):
                tok = row["token_id"]
                q = conn.execute(
                    "SELECT mid FROM paper_quotes WHERE token_id = ?", (tok,)
                ).fetchone()
                if q and q[0] is not None:
                    mtm = float(row["contracts"]) * float(q[0])
                    cost = float(row["notional_gross"]) + float(row["fee_entry_usd"])
                    unreal += mtm - cost

        return {
            "open_trades": int(open_rows["c"]),
            "open_cost_usd": float(open_rows["cost"]),
            "unrealized_pnl_usd_estimate": unreal,
            "settled_trades": int(settled["c"]),
            "realized_pnl_usd": float(settled["pnl"]),
            "settled_fees_usd": float(settled["fees"]),
            "taker_fee_bps": self.taker_fee_bps,
            "redeem_fee_bps": self.redeem_fee_bps,
        }

    def trades(self, limit: int = 200) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM paper_fills ORDER BY id DESC LIMIT ?", (limit,)
            )
            return [dict(r) for r in cur.fetchall()]


def settle_all_open_from_gamma(
    ledger: PaperLedger,
    *,
    gamma_base: str,
) -> tuple[int, list[str]]:
    """Settle all open fills; returns (rows_settled, error_messages)."""
    from pm_latency.connectors.gamma import DEFAULT_GAMMA_BASE, fetch_markets_by_condition_ids

    base = gamma_base or DEFAULT_GAMMA_BASE
    cids = ledger.distinct_open_condition_ids()
    errors: list[str] = []
    if not cids:
        return 0, []
    total = 0
    chunk = 15
    for i in range(0, len(cids), chunk):
        batch = cids[i : i + chunk]
        try:
            markets = fetch_markets_by_condition_ids(base, batch)
        except RuntimeError as e:
            errors.append(str(e))
            continue
        for m in markets:
            total += ledger.settle_from_gamma_market(m)
    return total, errors
