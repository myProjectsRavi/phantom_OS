"""Additional CLI coverage for runtime-facing commands."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

from click.testing import CliRunner

import phantom.cli as cli


def test_start_command_invokes_daemon(monkeypatch):
    started = {"value": False}; fake_daemon_mod = types.ModuleType("phantom.daemon")
    class _Daemon:
        def run(self): started["value"] = True
    fake_daemon_mod.PhantomDaemon = _Daemon
    monkeypatch.setitem(sys.modules, "phantom.daemon", fake_daemon_mod)
    result = CliRunner().invoke(cli.main, ["start"])
    assert result.exit_code == 0 and started["value"] is True


def test_cli_runtime_commands(monkeypatch):
    runner = CliRunner(); approved = {"pattern": None, "emergency": False}
    class _Agent:
        def perceive(self): return SimpleNamespace(app_name="Terminal", window_title="Build", screen_type="terminal", elements=[{"id": "x"}], is_typing=False, idle_seconds=1.5)
        def current_intent(self): return SimpleNamespace(intent=SimpleNamespace(value="coding"), confidence=0.9, source_app="Terminal")
        def learned_patterns(self): return [SimpleNamespace(id="p1", name="Repeat Build", frequency=4, confidence=0.88, approved=False)]
        def approve_pattern(self, pattern_id): approved["pattern"] = pattern_id
        def predictions(self): return [SimpleNamespace(action_type=SimpleNamespace(value="app_activate"), target_app="Terminal", confidence=0.77, expected_in_seconds=12.0, source="markov")]
        def clipboard_history(self): return [{"type": "text", "content": "hello world"}]
        def undo(self): return SimpleNamespace(success=True)
        def emergency_stop(self): approved["emergency"] = True
    monkeypatch.setattr(cli, "_agent", lambda: _Agent())
    for args in (["perceive"], ["intent"], ["patterns"], ["patterns-approve", "p1"], ["predictions"], ["clipboard"], ["undo"], ["emergency-stop"]): assert runner.invoke(cli.main, args).exit_code == 0
    assert approved["pattern"] == "p1" and approved["emergency"] is True


def test_cli_runtime_empty_states(monkeypatch):
    runner = CliRunner()
    class _Agent:
        def perceive(self): return None
        def current_intent(self): return None
        def learned_patterns(self): return []
        def predictions(self): return []
        def clipboard_history(self): return []
        def undo(self): return SimpleNamespace(success=False)
    monkeypatch.setattr(cli, "_agent", lambda: _Agent())
    for args in (["perceive"], ["intent"], ["patterns"], ["predictions"], ["clipboard"], ["undo"]): assert runner.invoke(cli.main, args).exit_code == 0
