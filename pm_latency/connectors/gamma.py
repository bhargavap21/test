"""Polymarket Gamma public HTTP API (events list)."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote

DEFAULT_GAMMA_BASE = "https://gamma-api.polymarket.com"


def fetch_events_by_slug(
    base_url: str,
    slug: str,
    *,
    timeout_s: float = 30.0,
) -> list[dict[str, Any]]:
    """GET /events?slug=<slug>; returns JSON list (empty if unknown slug)."""
    root = base_url.rstrip("/")
    url = f"{root}/events?slug={quote(slug)}"
    ctx = ssl.create_default_context()
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "pm-latency/0.2 (+https://github.com/bhargavap21/test)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s, context=ctx) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gamma HTTP {e.code} for {url}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Gamma request failed for {url}: {e}") from e

    data = json.loads(body)
    if not isinstance(data, list):
        raise RuntimeError(f"Gamma: expected list, got {type(data)}")
    return [x for x in data if isinstance(x, dict)]
