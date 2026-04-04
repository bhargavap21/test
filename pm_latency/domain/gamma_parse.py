"""Map Gamma `/events` payloads into `TradedMarket` rows."""

from __future__ import annotations

import json
from typing import Any

from pm_latency.domain.models import TradedMarket
from pm_latency.domain.short_crypto import parse_event_slug


def _parse_json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for x in data:
        if isinstance(x, str):
            out.append(x)
    return out


def _as_bool(v: Any) -> bool:
    return bool(v)


def _as_float(v: Any) -> float:
    if isinstance(v, bool) or v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v))
    except ValueError:
        return 0.0


def event_to_traded_markets(event: dict[str, Any]) -> list[TradedMarket]:
    """Extract short crypto Up/Down markets from a Gamma event object."""
    slug = str(event.get("slug") or "")
    parsed = parse_event_slug(slug)
    if parsed is None:
        return []

    asset, window_seconds, window_start_ts = parsed
    event_id = str(event.get("id") or "")
    title = str(event.get("title") or "")
    event_description = str(event.get("description") or "")
    event_resolution = str(event.get("resolutionSource") or "")

    markets_raw = event.get("markets")
    if not isinstance(markets_raw, list):
        return []

    rows: list[TradedMarket] = []
    for m in markets_raw:
        if not isinstance(m, dict):
            continue
        condition_id = str(m.get("conditionId") or "")
        market_id = str(m.get("id") or "")
        if not condition_id or not market_id:
            continue

        outcomes = tuple(_parse_json_list(m.get("outcomes")))
        token_ids = tuple(_parse_json_list(m.get("clobTokenIds")))
        if len(outcomes) != len(token_ids):
            # Skip malformed pairs; CLOB needs both sides.
            continue

        market_description = str(m.get("description") or "") or event_description
        resolution = str(m.get("resolutionSource") or "") or event_resolution

        rows.append(
            TradedMarket(
                condition_id=condition_id,
                market_id=market_id,
                event_id=event_id,
                event_slug=slug,
                market_slug=str(m.get("slug") or slug),
                asset=asset,
                window_seconds=window_seconds,
                window_start_ts=window_start_ts,
                title=title,
                question=str(m.get("question") or title),
                description=market_description,
                resolution_source=resolution,
                tick_size=_as_float(m.get("orderPriceMinTickSize")),
                neg_risk=_as_bool(m.get("negRisk")),
                accepting_orders=_as_bool(m.get("acceptingOrders")),
                closed=_as_bool(m.get("closed")),
                active=_as_bool(m.get("active")),
                outcomes=outcomes,
                token_ids=token_ids,
                end_date=m.get("endDate") if isinstance(m.get("endDate"), str) else None,
            )
        )

    return rows
