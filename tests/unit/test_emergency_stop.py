"""Test emergency stop gesture handling."""

from __future__ import annotations

import phantom.safety.emergency as emergency_module
from phantom.safety.emergency import EmergencyStop


class _DummySafety:
    def __init__(self):
        self.calls = 0

    def emergency_stop(self):
        self.calls += 1


def test_emergency_stop_triggers_on_three_quick_escapes(monkeypatch):
    safety = _DummySafety()
    stop = EmergencyStop(safety)
    times = iter([1.00, 1.20, 1.35])
    notified: list[tuple[str, int]] = []

    monkeypatch.setattr(emergency_module.time, "time", lambda: next(times))
    monkeypatch.setattr(
        emergency_module,
        "notification_script",
        lambda title, body: f"{title}::{body}",
    )
    monkeypatch.setattr(
        emergency_module,
        "run_osascript",
        lambda script, timeout: notified.append((script, timeout)),
    )

    stop.on_key("escape")
    stop.on_key("escape")
    assert safety.calls == 0

    stop.on_key("escape")
    assert safety.calls == 1
    assert stop._times == []
    assert notified == [("PHANTOM Emergency Stop::All actions stopped", 3)]


def test_non_escape_resets_key_buffer():
    safety = _DummySafety()
    stop = EmergencyStop(safety)
    stop._times = [1.0, 1.1]

    stop.on_key("enter")

    assert stop._times == []
    assert safety.calls == 0


def test_notification_errors_are_swallowed(monkeypatch):
    safety = _DummySafety()
    stop = EmergencyStop(safety)
    times = iter([5.00, 5.10, 5.20])

    monkeypatch.setattr(emergency_module.time, "time", lambda: next(times))
    monkeypatch.setattr(emergency_module, "notification_script", lambda *_args: "noop")
    monkeypatch.setattr(
        emergency_module,
        "run_osascript",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("osascript unavailable")),
    )

    stop.on_key("escape")
    stop.on_key("escape")
    stop.on_key("escape")

    assert safety.calls == 1
