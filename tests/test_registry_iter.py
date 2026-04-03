import json
import sqlite3
from pathlib import Path

from pm_latency.domain.registry import MarketRegistry


def _insert(conn, condition_id: str, accepting: int, closed: int) -> None:
    conn.execute(
        """
        INSERT INTO markets (
            condition_id, market_id, event_id, event_slug, market_slug,
            asset, window_seconds, window_start_ts,
            title, question, description, resolution_source,
            tick_size, neg_risk, accepting_orders, closed, active,
            outcomes_json, token_ids_json, end_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            condition_id,
            "mid",
            "eid",
            "slug",
            "slug",
            "btc",
            900,
            1,
            "t",
            "q",
            "d",
            "r",
            0.01,
            0,
            accepting,
            closed,
            1,
            json.dumps(["Up", "Down"]),
            json.dumps(["1", "2"]),
            None,
        ),
    )


def test_iter_tradable_filters(tmp_path: Path):
    db = tmp_path / "m.db"
    MarketRegistry(db)
    with sqlite3.connect(db) as conn:
        _insert(conn, "0xa", accepting=1, closed=0)
        _insert(conn, "0xb", accepting=0, closed=0)
        _insert(conn, "0xc", accepting=1, closed=1)
        conn.commit()

    reg = MarketRegistry(db)
    tradable = list(reg.iter_tradable())
    assert len(tradable) == 1
    assert tradable[0].condition_id == "0xa"

    all_rows = list(reg.iter_all())
    assert len(all_rows) == 3
