"""Release-gate coverage for daemon control-plane and lifecycle branches."""

from __future__ import annotations

import asyncio
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

import phantom.daemon as daemon_module
from phantom.daemon import PhantomDaemon
from phantom.models import (
    ActionResult,
    IntentResult,
    IntentType,
    PerceptionFrame,
    PhantomActionType,
    PredictedAction,
    TrustLevel,
)


class _Reader:
    def __init__(self, payload):
        self.payload = payload

    async def readline(self):
        if isinstance(self.payload, BaseException):
            raise self.payload
        return self.payload


class _Writer:
    def __init__(self):
        self.data = b""
        self.drained = False
        self.closed = False
        self.waited = False

    def write(self, data):
        self.data += data

    async def drain(self):
        self.drained = True

    def close(self):
        self.closed = True

    async def wait_closed(self):
        self.waited = True


class _Agent:
    frame_interval = 0.01

    def __init__(self):
        self.status = {"running": True}
        self._safety = SimpleNamespace(resume=lambda: None)
        self._executor = SimpleNamespace(undo_last_async=self._undo)

    async def _undo(self):
        return ActionResult(success=True, action_type=PhantomActionType.WAIT)

    def stats(self):
        return {"frames_processed": 2}

    def set_trust_level(self, _level):
        return None

    def emergency_stop(self):
        return None

    def clipboard_history(self, limit):
        return [{"content": str(limit)}]

    def perceive(self):
        return PerceptionFrame(
            app_name="Terminal",
            window_title="Build",
            screen_type="terminal",
            elements=[SimpleNamespace()],
            is_typing=True,
            idle_seconds=1.5,
        )

    def current_intent(self):
        return IntentResult(
            intent=IntentType.CODING,
            confidence=0.8,
            source_app="Terminal",
        )

    def predictions(self):
        return [
            PredictedAction(
                action_type=PhantomActionType.APP_ACTIVATE,
                target_app="Terminal",
                confidence=0.7,
                expected_in_seconds=4.0,
                source="markov",
            )
        ]


def _daemon_with_agent(tmp_path):
    daemon = object.__new__(PhantomDaemon)
    daemon._agent = _Agent()
    daemon._config_path = tmp_path / "config.toml"
    daemon._running = False
    daemon._previous_app = ""
    daemon._app_switch_time = 0.0
    daemon._last_schedule_check = None
    daemon._last_discovery = 0.0
    daemon._pid_file = tmp_path / "phantom.pid"
    daemon._lock_file = tmp_path / "phantom.lock"
    daemon._lock_handle = None
    daemon._socket_path = tmp_path / "phantom.sock"
    daemon._control_server = None
    return daemon


def test_start_control_server_creates_private_socket(tmp_path, monkeypatch):
    daemon = _daemon_with_agent(tmp_path)
    server = SimpleNamespace()
    captured = {}

    async def fake_start(handler, path):
        captured["handler"] = handler
        captured["path"] = path
        Path(path).write_text("")
        return server

    monkeypatch.setattr(daemon_module.asyncio, "start_unix_server", fake_start)
    asyncio.run(daemon._start_control_server())

    assert daemon._control_server is server
    assert captured["path"] == str(daemon._socket_path)
    assert stat.S_IMODE(daemon._socket_path.stat().st_mode) == 0o600


def test_control_client_success_and_error(tmp_path, monkeypatch):
    daemon = _daemon_with_agent(tmp_path)
    monkeypatch.setattr(daemon_module.logger, "warning", lambda *_args, **_kwargs: None)

    writer = _Writer()
    asyncio.run(daemon._handle_control_client(_Reader(b'{"command":"status"}\n'), writer))
    assert b'"ok": true' in writer.data
    assert writer.drained and writer.closed and writer.waited

    bad_writer = _Writer()
    asyncio.run(daemon._handle_control_client(_Reader(b"not-json\n"), bad_writer))
    assert b'"ok": false' in bad_writer.data
    assert b"Expecting value" in bad_writer.data


def test_control_command_serializes_nonempty_runtime_state(tmp_path):
    daemon = _daemon_with_agent(tmp_path)

    undo = asyncio.run(daemon._handle_control_command({"command": "undo"}))
    assert undo["ok"] is True
    assert undo["undone"] is True
    assert undo["action_type"] == "wait"

    frame = asyncio.run(daemon._handle_control_command({"command": "perceive"}))
    assert frame["frame"] == {
        "app_name": "Terminal",
        "window_title": "Build",
        "screen_type": "terminal",
        "elements": 1,
        "is_typing": True,
        "idle_seconds": 1.5,
    }

    intent = asyncio.run(daemon._handle_control_command({"command": "intent"}))
    assert intent["intent"]["intent"] == "coding"
    assert intent["intent"]["source_app"] == "Terminal"

    predictions = asyncio.run(daemon._handle_control_command({"command": "predictions"}))
    assert predictions["predictions"][0]["action_type"] == "app_activate"
    assert predictions["predictions"][0]["expected_in_seconds"] == 4.0


def test_control_command_empty_perception_intent_and_failed_undo(tmp_path):
    daemon = _daemon_with_agent(tmp_path)
    daemon._agent.perceive = lambda: None
    daemon._agent.current_intent = lambda: None

    async def failed_undo():
        return ActionResult(
            success=False,
            action_type=PhantomActionType.WAIT,
            error="cannot undo",
        )

    daemon._agent._executor.undo_last_async = failed_undo
    assert asyncio.run(daemon._handle_control_command({"command": "perceive"}))["frame"] is None
    assert asyncio.run(daemon._handle_control_command({"command": "intent"}))["intent"] is None
    result = asyncio.run(daemon._handle_control_command({"command": "undo"}))
    assert result["undone"] is False and result["error"] == "cannot undo"


def test_persist_trust_level_replaces_inserts_and_creates_section(tmp_path):
    daemon = _daemon_with_agent(tmp_path)

    daemon._config_path.write_text('[phantom]\ntrust_level = "approve_new"\n[other]\nx = 1\n')
    daemon._persist_trust_level(TrustLevel.AUTO_EXECUTE)
    text = daemon._config_path.read_text()
    assert 'trust_level = "auto_execute"' in text
    assert stat.S_IMODE(daemon._config_path.stat().st_mode) == 0o600

    daemon._config_path.write_text("[phantom]\nmax_actions_per_minute = 5\n[other]\nx = 1\n")
    daemon._persist_trust_level(TrustLevel.APPROVE_EACH)
    lines = daemon._config_path.read_text().splitlines()
    other_index = lines.index("[other]")
    assert lines[other_index - 1] == 'trust_level = "approve_each"'

    daemon._config_path.write_text("[other]\nx = 1\n")
    daemon._persist_trust_level(TrustLevel.SUGGEST_ONLY)
    text = daemon._config_path.read_text()
    assert "[phantom]" in text
    assert 'trust_level = "suggest_only"' in text


def test_run_async_calls_server_then_loop(tmp_path, monkeypatch):
    daemon = _daemon_with_agent(tmp_path)
    calls = []

    async def start():
        calls.append("server")

    async def loop():
        calls.append("loop")

    monkeypatch.setattr(daemon, "_start_control_server", start)
    monkeypatch.setattr(daemon, "_loop", loop)
    asyncio.run(daemon._run_async())
    assert calls == ["server", "loop"]


def test_release_lock_and_cleanup_helpers(tmp_path, monkeypatch):
    daemon = _daemon_with_agent(tmp_path)
    daemon._release_instance_lock()

    class _Handle:
        def __init__(self):
            self.closed = False

        def fileno(self):
            return 9

        def close(self):
            self.closed = True

    handle = _Handle()
    daemon._lock_handle = handle
    calls = []
    monkeypatch.setattr(daemon_module.fcntl, "flock", lambda fd, flag: calls.append((fd, flag)))
    daemon._release_instance_lock()
    assert handle.closed is True
    assert daemon._lock_handle is None
    assert calls == [(9, daemon_module.fcntl.LOCK_UN)]

    daemon._pid_file.write_text("1")
    daemon._socket_path.write_text("")
    daemon._cleanup_pid()
    daemon._cleanup_control_socket()
    assert not daemon._pid_file.exists()
    assert not daemon._socket_path.exists()


def test_handle_signal_and_status(tmp_path, monkeypatch):
    daemon = _daemon_with_agent(tmp_path)
    daemon._running = True
    monkeypatch.setattr(daemon_module.logger, "info", lambda *_args, **_kwargs: None)
    daemon._handle_signal(15, None)
    assert daemon._running is False
    assert daemon.status() == {"running": True}


def test_loop_logs_tick_error_and_stops(tmp_path, monkeypatch):
    daemon = _daemon_with_agent(tmp_path)
    daemon._running = True
    seen = []

    async def tick():
        daemon._running = False
        raise RuntimeError("tick")

    async def sleep(delay):
        seen.append(delay)

    monkeypatch.setattr(daemon, "_tick", tick)
    monkeypatch.setattr(daemon_module.asyncio, "sleep", sleep)
    monkeypatch.setattr(daemon_module.logger, "error", lambda *_args, **_kwargs: None)
    asyncio.run(daemon._loop())
    assert seen == [daemon._agent.frame_interval]
