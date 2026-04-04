"""EWMA estimate of log-return variance per second (annualized sigma)."""

from __future__ import annotations

import math
from collections import deque


class EwmaVol:
    """Track EWMA of (log return)^2 / dt to approximate variance per second."""

    def __init__(
        self,
        *,
        half_life_seconds: float = 300.0,
        min_updates: int = 5,
        max_history: int = 500,
    ) -> None:
        if half_life_seconds <= 0:
            raise ValueError("half_life_seconds must be positive")
        self._lambda = 1.0 - math.pow(0.5, 1.0 / half_life_seconds)
        self._min_updates = min_updates
        self._history: deque[float] = deque(maxlen=max_history)
        self._var_per_s = 0.0
        self._n_updates = 0
        self._last_mid: float | None = None
        self._last_ts_ms: int | None = None

    def update(self, mid: float, ts_ms: int | None) -> None:
        if mid <= 0:
            return
        if self._last_mid is None or self._last_mid <= 0:
            self._last_mid = mid
            self._last_ts_ms = ts_ms
            return

        r = math.log(mid / self._last_mid)
        if ts_ms is not None and self._last_ts_ms is not None:
            dt_s = max((ts_ms - self._last_ts_ms) / 1000.0, 1e-3)
        else:
            dt_s = 1.0
        inst = (r * r) / dt_s
        self._history.append(inst)
        self._var_per_s = self._lambda * inst + (1.0 - self._lambda) * self._var_per_s
        self._n_updates += 1
        self._last_mid = mid
        self._last_ts_ms = ts_ms

    def sigma_annual(self) -> float:
        if self._n_updates < self._min_updates or self._var_per_s <= 0:
            return 0.0
        sec_per_year = 365.25 * 24 * 3600
        return math.sqrt(self._var_per_s * sec_per_year)
