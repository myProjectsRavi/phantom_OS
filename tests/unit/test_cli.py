"""Coverage tests for CLI commands."""

from __future__ import annotations

import signal
import stat
from types import SimpleNamespace

from click.testing import CliRunner

import phantom.cli as cli


def test_init_creates_private_local_layout(tmp_path, monkeypatch):
    runner = CliRunner(); monkeypatch.setattr(cli.Path, "home", lambda: tmp_path)
    result = runner.invoke(cli.main, ["init"]); assert result.exit_code == 0
    root = tmp_path / ".phantom"
    assert (root / "recipes").exists() and (root / "logs").exists() and (root / "config.toml").exists()
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE((root / "recipes").stat().st_mode) == 0o700
    assert stat.S_IMODE((root / "logs").stat().st_mode) == 0o700
    assert stat.S_IMODE((root / "config.toml").stat().st_mode) == 0o600


def test_stop_without_live_control_cleans_stale_state(tmp_path, monkeypatch):
    runner = CliRunner(); monkeypatch.setattr(cli.Path, "home", lambda: tmp_path)
    control = tmp_path / ".phantom" / "phantom.sock"; monkeypatch.setattr(cli, "socket_path", lambda: control)
    def unavailable(_command): raise cli.DaemonUnavailable("not running")
    monkeypatch.setattr(cli, "send_command", unavailable)
    root = tmp_path / ".phantom"; root.mkdir(parents=True); pid_file = root / "phantom.pid"; pid_file.write_text("1234"); control.write_text("")
    result = runner.invoke(cli.main, ["stop"]); assert result.exit_code == 0
    assert not pid_file.exists() and not control.exists()


def test_stop_signals_pid_proven_by_live_control(tmp_path, monkeypatch):
    runner = CliRunner(); monkeypatch.setattr(cli.Path, "home", lambda: tmp_path); monkeypatch.setattr(cli, "send_command", lambda command: {"ok": True, "pid": 1234})
    sent = []; monkeypatch.setattr(cli.os, "kill", lambda pid, sig: sent.append((pid, sig)))
    result = runner.invoke(cli.main, ["stop"]); assert result.exit_code == 0
    assert sent == [(1234, 0), (1234, signal.SIGTERM)]
    pid_file = tmp_path / ".phantom" / "phantom.pid"; assert pid_file.read_text() == "1234"; assert stat.S_IMODE(pid_file.stat().st_mode) == 0o600


def test_stop_repairs_stale_pid_and_never_signals_it(tmp_path, monkeypatch):
    runner = CliRunner(); monkeypatch.setattr(cli.Path, "home", lambda: tmp_path); monkeypatch.setattr(cli, "send_command", lambda command: {"ok": True, "pid": 5678})
    pid_file = tmp_path / ".phantom" / "phantom.pid"; pid_file.parent.mkdir(parents=True, exist_ok=True); pid_file.write_text("1234")
    sent = []; monkeypatch.setattr(cli.os, "kill", lambda pid, sig: sent.append((pid, sig)))
    result = runner.invoke(cli.main, ["stop"]); assert result.exit_code == 0
    assert sent == [(5678, 0), (5678, signal.SIGTERM)] and all(pid != 1234 for pid, _sig in sent) and pid_file.read_text() == "5678"


def test_stop_rejects_invalid_live_process_identity(tmp_path, monkeypatch):
    runner = CliRunner(); monkeypatch.setattr(cli.Path, "home", lambda: tmp_path); monkeypatch.setattr(cli, "send_command", lambda command: {"ok": True, "pid": "not-a-pid"})
    sent = []; monkeypatch.setattr(cli.os, "kill", lambda pid, sig: sent.append((pid, sig)))
    result = runner.invoke(cli.main, ["stop"]); assert result.exit_code != 0; assert "invalid process identity" in result.output; assert sent == []


def test_status_and_stats_commands(monkeypatch):
    runner = CliRunner()
    def fake_daemon(command, **_payload):
        if command == "status": return {"ok": True, "status": {"running": True, "stats": {"frames_processed": 1}}}
        if command == "stats": return {"ok": True, "stats": {"frames_processed": 3, "actions_executed": 4, "patterns_discovered": 1, "recipes_run": 1, "uptime_seconds": 5}}
        raise AssertionError(command)
    monkeypatch.setattr(cli, "_daemon", fake_daemon)
    assert runner.invoke(cli.main, ["status"]).exit_code == 0 and runner.invoke(cli.main, ["stats"]).exit_code == 0


def test_trust_emergency_resume_and_undo_use_daemon(monkeypatch):
    runner = CliRunner(); calls = []
    def fake_daemon(command, **payload):
        calls.append((command, payload)); return {"ok": True, "undone": True} if command == "undo" else {"ok": True}
    monkeypatch.setattr(cli, "_daemon", fake_daemon)
    for args in (["trust", "approve_each"], ["emergency-stop"], ["resume-actions"], ["undo"]): assert runner.invoke(cli.main, args).exit_code == 0
    assert calls == [("trust", {"level": "approve_each"}), ("emergency_stop", {}), ("resume", {}), ("undo", {})]


def test_recipe_commands_use_interactive_agent(monkeypatch):
    runner = CliRunner(); state = {"run_name": None}
    class _Agent:
        def run_recipe(self, name): state["run_name"] = name; return {"success": True, "duration_ms": 8}
        def list_recipes(self): return [SimpleNamespace(name="demo", source="builtin", trigger=None, run_count=2, enabled=True)]
    monkeypatch.setattr(cli, "_agent", lambda: _Agent()); monkeypatch.setattr(cli, "_run", lambda value: value)
    assert runner.invoke(cli.main, ["recipes", "list"]).exit_code == 0
    assert runner.invoke(cli.main, ["recipes", "run", "demo"]).exit_code == 0
    assert state["run_name"] == "demo"
