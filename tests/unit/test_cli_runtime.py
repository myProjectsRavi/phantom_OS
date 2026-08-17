"""Additional CLI coverage for runtime-facing commands."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

from click.testing import CliRunner

import phantom.cli as cli


def test_start_command_invokes_daemon(monkeypatch):
    started = {"value": False}
    fake_daemon_mod = types.ModuleType("phantom.daemon")

    class _Daemon:
        def run(self):
            started["value"] = True

    fake_daemon_mod.PhantomDaemon = _Daemon
    monkeypatch.setitem(sys.modules, "phantom.daemon", fake_daemon_mod)
    monkeypatch.setattr(
        cli,
        "send_command",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(cli.DaemonUnavailable("stopped")),
    )
    result = CliRunner().invoke(cli.main, ["start"])
    assert result.exit_code == 0 and started["value"] is True


def test_cli_runtime_commands(monkeypatch):
    runner = CliRunner()
    approved = {"pattern": None, "emergency": False}

    class _Agent:
        def learned_patterns(self):
            return [
                SimpleNamespace(
                    id="p1", name="Repeat Build", frequency=4, confidence=0.88, approved=False
                )
            ]

        def approve_pattern(self, pattern_id):
            approved["pattern"] = pattern_id

    def _daemon(command, **payload):
        del payload
        responses = {
            "perceive": {
                "ok": True,
                "frame": {
                    "app_name": "Terminal",
                    "window_title": "Build",
                    "screen_type": "terminal",
                    "elements": [{"id": "x"}],
                    "is_typing": False,
                    "idle_seconds": 1.5,
                },
            },
            "intent": {
                "ok": True,
                "intent": {"intent": "coding", "confidence": 0.9, "source_app": "Terminal"},
            },
            "predictions": {
                "ok": True,
                "predictions": [
                    {
                        "action_type": "app_activate",
                        "target_app": "Terminal",
                        "confidence": 0.77,
                        "expected_in_seconds": 12.0,
                        "source": "markov",
                    }
                ],
            },
            "clipboard_history": {
                "ok": True,
                "history": [{"type": "text", "content": "hello world"}],
            },
            "undo": {"ok": True, "undone": True},
            "emergency_stop": {"ok": True},
        }
        if command == "emergency_stop":
            approved["emergency"] = True
        return responses[command]

    monkeypatch.setattr(cli, "_agent", lambda: _Agent())
    monkeypatch.setattr(cli, "_daemon", _daemon)
    for args in (
        ["perceive"],
        ["intent"],
        ["patterns"],
        ["patterns-approve", "p1"],
        ["predictions"],
        ["clipboard"],
        ["undo"],
        ["emergency-stop"],
    ):
        result = runner.invoke(cli.main, args)
        assert result.exit_code == 0, result.output
    assert approved["pattern"] == "p1" and approved["emergency"] is True


def test_cli_runtime_empty_states(monkeypatch):
    runner = CliRunner()

    class _Agent:
        def learned_patterns(self):
            return []

    responses = {
        "perceive": {"ok": True, "frame": None},
        "intent": {"ok": True, "intent": None},
        "predictions": {"ok": True, "predictions": []},
        "clipboard_history": {"ok": True, "history": []},
        "undo": {"ok": True, "undone": False},
    }
    monkeypatch.setattr(cli, "_agent", lambda: _Agent())
    monkeypatch.setattr(cli, "_daemon", lambda command, **_payload: responses[command])
    for args in (["perceive"], ["intent"], ["patterns"], ["predictions"], ["clipboard"], ["undo"]):
        result = runner.invoke(cli.main, args)
        assert result.exit_code == 0, result.output
