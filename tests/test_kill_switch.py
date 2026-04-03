from pathlib import Path

from pm_latency.risk.kill_switch import kill_switch_active


def test_kill_env():
    assert kill_switch_active(env_value="1", kill_file=None) is True
    assert kill_switch_active(env_value="true", kill_file=None) is True
    assert kill_switch_active(env_value="0", kill_file=None) is False
    assert kill_switch_active(env_value="", kill_file=None) is False


def test_kill_file(tmp_path: Path):
    k = tmp_path / "kill"
    assert kill_switch_active(env_value="", kill_file=k) is False
    k.write_text("x")
    assert kill_switch_active(env_value="", kill_file=k) is True
