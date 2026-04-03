"""Kill switch: env flag and optional filesystem tripwire."""

from __future__ import annotations

import os
from pathlib import Path


def kill_switch_active(
    *,
    env_value: str | None = None,
    kill_file: Path | None = None,
) -> bool:
    """
    True if trading must stop.

    Env `PM_KILL_SWITCH`: 1/true/yes/on (case-insensitive) => killed.
    If `kill_file` exists (non-empty path on disk) => killed.
    """
    raw = env_value if env_value is not None else os.environ.get("PM_KILL_SWITCH", "")
    if raw.strip().lower() in ("1", "true", "yes", "on"):
        return True
    if kill_file is not None and kill_file.exists():
        return True
    return False


def default_kill_file() -> Path:
    return Path(os.environ.get("PM_KILL_FILE", "data/kill"))
