"""Persistent risk counters (daily PnL, exposure, order rate timestamps)."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


def _utc_today() -> str:
    return date.today().isoformat()


@dataclass
class RiskState:
    day_utc: str = field(default_factory=_utc_today)
    daily_realized_pnl_usd: float = 0.0
    exposure_usd_by_condition: dict[str, float] = field(default_factory=dict)
    order_timestamps_unix: list[float] = field(default_factory=list)

    def reset_if_new_day(self) -> None:
        today = _utc_today()
        if self.day_utc != today:
            self.day_utc = today
            self.daily_realized_pnl_usd = 0.0
            self.exposure_usd_by_condition.clear()
            self.order_timestamps_unix.clear()

    def to_dict(self) -> dict[str, Any]:
        return {
            "day_utc": self.day_utc,
            "daily_realized_pnl_usd": self.daily_realized_pnl_usd,
            "exposure_usd_by_condition": dict(self.exposure_usd_by_condition),
            "order_timestamps_unix": list(self.order_timestamps_unix),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RiskState:
        return cls(
            day_utc=str(d.get("day_utc") or _utc_today()),
            daily_realized_pnl_usd=float(d.get("daily_realized_pnl_usd") or 0.0),
            exposure_usd_by_condition={
                str(k): float(v) for k, v in (d.get("exposure_usd_by_condition") or {}).items()
            },
            order_timestamps_unix=[float(x) for x in (d.get("order_timestamps_unix") or [])],
        )


def load_risk_state(path: Path) -> RiskState:
    if not path.exists():
        return RiskState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return RiskState()
    if not isinstance(data, dict):
        return RiskState()
    st = RiskState.from_dict(data)
    st.reset_if_new_day()
    return st


def save_risk_state(path: Path, state: RiskState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state.to_dict(), indent=2)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        Path(tmp).replace(path)
    except OSError:
        Path(tmp).unlink(missing_ok=True)
        raise


def now_unix() -> float:
    return datetime.now(timezone.utc).timestamp()


def prune_order_times(times: list[float], *, now: float, window_s: float = 60.0) -> list[float]:
    cutoff = now - window_s
    return [t for t in times if t >= cutoff]
