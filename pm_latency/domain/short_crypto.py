"""Slug patterns and time alignment for short-horizon BTC/ETH Up/Down markets."""

from __future__ import annotations

import re
from typing import Literal

WINDOW_5M = 300
WINDOW_15M = 900

Asset = Literal["btc", "eth"]
Window = Literal[300, 900]

_SLUG_RE = re.compile(
    r"^(?P<asset>btc|eth)-updown-(?P<label>5m|15m)-(?P<ts>\d+)$",
    re.IGNORECASE,
)


def window_seconds_from_label(label: str) -> int:
    label = label.lower()
    if label == "5m":
        return WINDOW_5M
    if label == "15m":
        return WINDOW_15M
    raise ValueError(f"unknown window label: {label!r}")


def align_window_start(ts: int, window_seconds: int) -> int:
    """UTC window start for slug epoch (floor to window boundary)."""
    if window_seconds <= 0:
        raise ValueError("window_seconds must be positive")
    return ts - (ts % window_seconds)


def candidate_window_starts(now_ts: int, window_seconds: int) -> list[int]:
    """Previous, current, and next two window starts (for discovery polling)."""
    current = align_window_start(now_ts, window_seconds)
    return [
        current - window_seconds,
        current,
        current + window_seconds,
        current + 2 * window_seconds,
    ]


def build_event_slug(asset: Asset, window_seconds: int, window_start_ts: int) -> str:
    if window_seconds == WINDOW_5M:
        label = "5m"
    elif window_seconds == WINDOW_15M:
        label = "15m"
    else:
        raise ValueError(f"unsupported window: {window_seconds}")
    return f"{asset}-updown-{label}-{window_start_ts}"


def parse_event_slug(slug: str) -> tuple[Asset, int, int] | None:
    """Return (asset, window_seconds, window_start_ts) if slug matches short crypto pattern."""
    m = _SLUG_RE.match(slug.strip())
    if not m:
        return None
    asset = m.group("asset").lower()
    if asset not in ("btc", "eth"):
        return None
    window_seconds = window_seconds_from_label(m.group("label"))
    window_start_ts = int(m.group("ts"))
    return asset, window_seconds, window_start_ts
