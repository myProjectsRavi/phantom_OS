"""Coverage tests for PHANTOM background daemon runtime behavior."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

from phantom.daemon import PhantomDaemon
from phantom.models import PerceptionFrame, Recipe, TrustLevel


def test_run_starts_and_stops_agent(monkeypatch):
    events = []; fake_agent = SimpleNamespace(start=lambda: events.append("start"), stop=lambda: events.append("stop"), frame_interval=0.01)
    monkeypatch.setattr("phantom.daemon.PhantomAgent.init", lambda _path=None: fake_agent); daemon = PhantomDaemon()
    monkeypatch.setattr(daemon, "_write_pid", lambda: events.append("write_pid")); monkeypatch.setattr(daemon, "_cleanup_pid", lambda: events.append("cleanup_pid")); monkeypatch.setattr(daemon, "_cleanup_control_socket", lambda: events.append("cleanup_socket")); monkeypatch.setattr("phantom.daemon.signal.signal", lambda *_args, **_kwargs: None); monkeypatch.setattr("phantom.daemon.asyncio.run", lambda _coro: None)
    daemon.run(); assert events == ["start", "write_pid", "stop", "cleanup_socket", "cleanup_pid"]


def test_loop_handles_tick_errors_and_sleeps(monkeypatch):
    fake_agent = SimpleNamespace(frame_interval=0.25); monkeypatch.setattr("phantom.daemon.PhantomAgent.init", lambda _path=None: fake_agent); daemon = PhantomDaemon(); calls = {"ticks": 0}
    async def _tick():
        calls["ticks"] += 1
        if calls["ticks"] == 1: raise RuntimeError("tick failed")
        daemon._running = False
    sleeps = []
    async def _sleep(value): sleeps.append(value)
    daemon._running = True; monkeypatch.setattr(daemon, "_tick", _tick); monkeypatch.setattr("phantom.daemon.asyncio.sleep", _sleep); asyncio.run(daemon._loop())
    assert calls["ticks"] == 2 and sleeps == [0.25, 0.25]


def test_tick_runs_matching_triggers(monkeypatch):
    run_calls = []; discover_calls = []; intent_calls = []; frame = PerceptionFrame(app_name="Terminal", text_content={"line": "Error while compiling"}, idle_seconds=3.0)
    class _Agent:
        frame_interval = 0.1; status = {"running": True}
        def perceive(self): return frame
        def current_intent(self): intent_calls.append("intent"); return None
        def matching_recipes(self, event): return [Recipe(name=f"{event.type}_recipe", source="builtin")] if event.type in {"app_switch", "content_match", "schedule", "idle"} else []
        async def run_recipe(self, name): run_calls.append(name); return {"success": True}
        def discover_patterns(self): discover_calls.append("discover"); return []
    monkeypatch.setattr("phantom.daemon.PhantomAgent.init", lambda _path=None: _Agent()); daemon = PhantomDaemon(); daemon._last_discovery = 0.0; asyncio.run(daemon._tick())
    assert daemon._previous_app == "Terminal" and daemon._app_switch_time <= time.time() and intent_calls == ["intent"] and discover_calls == ["discover"]
    assert set(run_calls) == {"app_switch_recipe", "content_match_recipe", "schedule_recipe", "idle_recipe"}


def test_tick_returns_early_without_frame(monkeypatch):
    class _Agent:
        frame_interval = 0.1; status = {"running": True}
        def perceive(self): return None
        def current_intent(self): raise AssertionError("intent should not run without frame")
        def matching_recipes(self, _event): raise AssertionError("triggers should not run without frame")
        async def run_recipe(self, _name): raise AssertionError("recipes should not run without frame")
        def discover_patterns(self): raise AssertionError("discovery should not run without frame")
    monkeypatch.setattr("phantom.daemon.PhantomAgent.init", lambda _path=None: _Agent()); asyncio.run(PhantomDaemon()._tick())


def test_status_signal_and_pid_helpers(tmp_path, monkeypatch):
    fake_agent = SimpleNamespace(status={"running": True}, frame_interval=0.1); monkeypatch.setattr("phantom.daemon.PhantomAgent.init", lambda _path=None: fake_agent); monkeypatch.setattr("phantom.daemon.Path.home", lambda: Path(tmp_path)); daemon = PhantomDaemon(); daemon._running = True
    daemon._handle_signal(15, None); assert daemon._running is False and daemon.status() == {"running": True}; daemon._write_pid(); assert daemon._pid_file.exists(); daemon._cleanup_pid(); assert not daemon._pid_file.exists()


def test_control_commands_act_on_same_agent_and_persist_trust(tmp_path, monkeypatch):
    calls = []
    class _Safety:
        def resume(self): calls.append("resume")
    class _Executor:
        async def undo_last_async(self): return None
    class _Agent:
        status = {"running": True, "emergency_stopped": False}; _safety = _Safety(); _executor = _Executor()
        def stats(self): return {"frames_processed": 3}
        def set_trust_level(self, level): calls.append(("trust", level.value))
        def emergency_stop(self): calls.append("emergency")
        def clipboard_history(self, limit): return [{"content": str(limit)}]
        def perceive(self): return None
        def current_intent(self): return None
        def predictions(self): return []
    monkeypatch.setattr("phantom.daemon.PhantomAgent.init", lambda _path=None: _Agent()); daemon = PhantomDaemon(config_path=tmp_path / "config.toml")
    assert asyncio.run(daemon._handle_control_command({"command": "status"}))["ok"] and asyncio.run(daemon._handle_control_command({"command": "stats"}))["ok"]
    trust = asyncio.run(daemon._handle_control_command({"command": "trust", "level": TrustLevel.APPROVE_EACH.value})); assert trust["trust_level"] == "approve_each" and 'trust_level = "approve_each"' in (tmp_path / "config.toml").read_text()
    assert asyncio.run(daemon._handle_control_command({"command": "emergency_stop"}))["ok"] and asyncio.run(daemon._handle_control_command({"command": "resume"}))["ok"]
    assert asyncio.run(daemon._handle_control_command({"command": "undo"}))["undone"] is False
    assert asyncio.run(daemon._handle_control_command({"command": "clipboard_history", "limit": 7}))["history"] == [{"content": "7"}]
    assert calls == [("trust", "approve_each"), "emergency", "resume"]


def test_unknown_control_command_fails(monkeypatch):
    fake_agent = SimpleNamespace(frame_interval=0.1); monkeypatch.setattr("phantom.daemon.PhantomAgent.init", lambda _path=None: fake_agent); result = asyncio.run(PhantomDaemon()._handle_control_command({"command": "not-real"})); assert result["ok"] is False
