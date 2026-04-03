"""SQLite-backed registry of discovered markets."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path

from pm_latency.domain.models import TradedMarket

SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (
    condition_id TEXT PRIMARY KEY,
    market_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    event_slug TEXT NOT NULL,
    market_slug TEXT NOT NULL,
    asset TEXT NOT NULL,
    window_seconds INTEGER NOT NULL,
    window_start_ts INTEGER NOT NULL,
    title TEXT NOT NULL,
    question TEXT NOT NULL,
    description TEXT NOT NULL,
    resolution_source TEXT NOT NULL,
    tick_size REAL NOT NULL,
    neg_risk INTEGER NOT NULL,
    accepting_orders INTEGER NOT NULL,
    closed INTEGER NOT NULL,
    active INTEGER NOT NULL,
    outcomes_json TEXT NOT NULL,
    token_ids_json TEXT NOT NULL,
    end_date TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_markets_event_slug ON markets(event_slug);
CREATE INDEX IF NOT EXISTS idx_markets_window ON markets(asset, window_seconds, window_start_ts);
"""


class MarketRegistry:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.executescript(SCHEMA)

    def upsert_many(self, rows: Sequence[TradedMarket]) -> int:
        if not rows:
            return 0
        with sqlite3.connect(self.path) as conn:
            conn.executemany(
                """
                INSERT INTO markets (
                    condition_id, market_id, event_id, event_slug, market_slug,
                    asset, window_seconds, window_start_ts,
                    title, question, description, resolution_source,
                    tick_size, neg_risk, accepting_orders, closed, active,
                    outcomes_json, token_ids_json, end_date, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, datetime('now')
                )
                ON CONFLICT(condition_id) DO UPDATE SET
                    market_id = excluded.market_id,
                    event_id = excluded.event_id,
                    event_slug = excluded.event_slug,
                    market_slug = excluded.market_slug,
                    asset = excluded.asset,
                    window_seconds = excluded.window_seconds,
                    window_start_ts = excluded.window_start_ts,
                    title = excluded.title,
                    question = excluded.question,
                    description = excluded.description,
                    resolution_source = excluded.resolution_source,
                    tick_size = excluded.tick_size,
                    neg_risk = excluded.neg_risk,
                    accepting_orders = excluded.accepting_orders,
                    closed = excluded.closed,
                    active = excluded.active,
                    outcomes_json = excluded.outcomes_json,
                    token_ids_json = excluded.token_ids_json,
                    end_date = excluded.end_date,
                    updated_at = datetime('now')
                """,
                [_row_tuple(r) for r in rows],
            )
        return len(rows)

    def count(self) -> int:
        with sqlite3.connect(self.path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM markets").fetchone()
        return int(row[0]) if row else 0


def _row_tuple(r: TradedMarket) -> tuple:
    import json

    return (
        r.condition_id,
        r.market_id,
        r.event_id,
        r.event_slug,
        r.market_slug,
        r.asset,
        r.window_seconds,
        r.window_start_ts,
        r.title,
        r.question,
        r.description,
        r.resolution_source,
        r.tick_size,
        1 if r.neg_risk else 0,
        1 if r.accepting_orders else 0,
        1 if r.closed else 0,
        1 if r.active else 0,
        json.dumps(list(r.outcomes)),
        json.dumps(list(r.token_ids)),
        r.end_date,
    )
