"""Smoke tests for CLI argument and env resolution."""

from __future__ import annotations

from pm_latency.ops import runner


def test_dry_run_default(monkeypatch):
    monkeypatch.delenv("DRY_RUN", raising=False)
    assert runner._env_dry_run() is True
    monkeypatch.setenv("DRY_RUN", "0")
    assert runner._env_dry_run() is False


def test_main_respects_flags(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "0")
    code = runner.main(["--dry-run"])
    assert code == 0

    monkeypatch.setenv("DRY_RUN", "1")
    code = runner.main(["--live"])
    assert code == 0


def test_main_env_only(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "1")
    assert runner.main([]) == 0
