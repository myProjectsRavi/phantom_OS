"""Release-gate coverage for control framing and native action adapters."""

from __future__ import annotations

import json
import socket
from types import SimpleNamespace

import pytest

import phantom.actions.app_control as app_module
import phantom.actions.clipboard as clipboard_module
import phantom.actions.keyboard as keyboard_module
import phantom.control as control
from phantom.actions.app_control import AppController
from phantom.actions.clipboard import ClipboardManager
from phantom.actions.keyboard import KeyboardSimulator


class _FakeSocket:
    def __init__(self, chunks=None, *, connect_error=None):
        self.chunks = list(chunks or [])
        self.connect_error = connect_error
        self.timeout = None
        self.connected = None
        self.sent = b""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False

    def settimeout(self, value):
        self.timeout = value

    def connect(self, path):
        if self.connect_error is not None:
            raise self.connect_error
        self.connected = path

    def sendall(self, data):
        self.sent += data

    def recv(self, _size):
        return self.chunks.pop(0) if self.chunks else b""


def _socket_factory(fake):
    def factory(family, sock_type):
        assert family == socket.AF_UNIX
        assert sock_type == socket.SOCK_STREAM
        return fake

    return factory


def test_control_socket_path_and_missing_daemon(tmp_path, monkeypatch):
    monkeypatch.setattr(control.Path, "home", lambda: tmp_path)
    assert control.socket_path() == tmp_path / ".phantom" / "phantom.sock"
    with pytest.raises(control.DaemonUnavailable, match="not running"):
        control.send_command("status")


def test_control_send_command_round_trip(tmp_path, monkeypatch):
    path = tmp_path / "phantom.sock"
    path.write_text("")
    monkeypatch.setattr(control, "socket_path", lambda: path)
    fake = _FakeSocket([b'{"ok":true,"pid":12}\ntrailing'])
    monkeypatch.setattr(control.socket, "socket", _socket_factory(fake))

    response = control.send_command("trust", level="approve_each")

    assert response == {"ok": True, "pid": 12}
    assert fake.timeout == 3.0
    assert fake.connected == str(path)
    assert json.loads(fake.sent.decode().strip()) == {
        "command": "trust",
        "level": "approve_each",
    }


def test_control_send_command_collects_chunks_until_eof(tmp_path, monkeypatch):
    path = tmp_path / "phantom.sock"
    path.write_text("")
    monkeypatch.setattr(control, "socket_path", lambda: path)
    fake = _FakeSocket([b'{"ok":', b"true}", b""])
    monkeypatch.setattr(control.socket, "socket", _socket_factory(fake))
    assert control.send_command("status") == {"ok": True}


@pytest.mark.parametrize(
    "error",
    [FileNotFoundError(), ConnectionError(), OSError(), socket.timeout()],
)
def test_control_transport_errors_fail_closed(tmp_path, monkeypatch, error):
    path = tmp_path / "phantom.sock"
    path.write_text("")
    monkeypatch.setattr(control, "socket_path", lambda: path)
    fake = _FakeSocket(connect_error=error)
    monkeypatch.setattr(control.socket, "socket", _socket_factory(fake))
    with pytest.raises(control.DaemonUnavailable, match="unavailable"):
        control.send_command("status")


def test_control_empty_and_invalid_responses_fail_closed(tmp_path, monkeypatch):
    path = tmp_path / "phantom.sock"
    path.write_text("")
    monkeypatch.setattr(control, "socket_path", lambda: path)

    empty = _FakeSocket([b""])
    monkeypatch.setattr(control.socket, "socket", _socket_factory(empty))
    with pytest.raises(control.DaemonUnavailable, match="no control response"):
        control.send_command("status")

    invalid = _FakeSocket([b"[]\n"])
    monkeypatch.setattr(control.socket, "socket", _socket_factory(invalid))
    with pytest.raises(control.DaemonUnavailable, match="invalid control response"):
        control.send_command("status")


def test_app_controller_failure_and_success_paths(monkeypatch):
    controller = AppController()
    monkeypatch.setattr(app_module, "escape_applescript", lambda value: f"safe:{value}")

    monkeypatch.setattr(
        app_module,
        "run_osascript",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=2, stdout=""),
    )
    failed = controller.activate("Notes")
    assert failed.success is False and "exited with 2" in failed.error

    monkeypatch.setattr(
        app_module,
        "run_osascript",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert controller.activate("Notes").error == "boom"

    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(app_module.subprocess, "run", fake_run)
    assert controller.open_url("https://example.com").success is True
    assert calls[-1] == ["open", "https://example.com"]
    assert controller.open_url("file:///tmp/a").success is False
    assert controller.open_url("not-a-url").success is False

    monkeypatch.setattr(
        app_module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=3),
    )
    assert "exited with 3" in controller.open_url("https://example.com").error
    assert "exited with 3" in controller.open_file("/tmp/a").error

    monkeypatch.setattr(
        app_module.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("open failed")),
    )
    assert controller.open_url("https://example.com").error == "open failed"
    assert controller.open_file("/tmp/a").error == "open failed"


def test_app_controller_running_list_paths(monkeypatch):
    controller = AppController()
    monkeypatch.setattr(
        app_module,
        "run_osascript",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout="ignored"),
    )
    assert controller.list_running() == []
    monkeypatch.setattr(
        app_module,
        "run_osascript",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="Safari, Notes, "),
    )
    assert controller.list_running() == ["Safari", "Notes"]


def test_clipboard_manager_failure_paths_and_classification(monkeypatch):
    manager = ClipboardManager(max_history=2)
    monkeypatch.setattr(
        clipboard_module,
        "run_osascript",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1),
    )
    with pytest.raises(RuntimeError, match="copy shortcut"):
        manager.copy()
    with pytest.raises(RuntimeError, match="paste shortcut"):
        manager.paste()

    monkeypatch.setattr(
        clipboard_module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout=""),
    )
    with pytest.raises(RuntimeError, match="pbpaste"):
        manager.get()

    class _BadProc:
        returncode = 1

        def communicate(self, _payload):
            return None

    monkeypatch.setattr(clipboard_module.subprocess, "Popen", lambda *_args, **_kwargs: _BadProc())
    with pytest.raises(RuntimeError, match="pbcopy"):
        manager.set("value")

    assert manager._classify("https://example.com") == "url"
    assert manager._classify("def run(): pass") == "code"
    assert manager._classify("user@example.com") == "email"
    assert manager._classify("plain") == "text"


def test_clipboard_manager_history_search_and_paste(monkeypatch):
    manager = ClipboardManager(max_history=2)
    times = iter([1.0, 2.0, 3.0])
    monkeypatch.setattr(clipboard_module.time, "time", lambda: next(times))
    manager._add("first")
    manager._add("Second URL https://example.com")
    manager._add("third")
    assert [item["content"] for item in manager.history(10)] == [
        "Second URL https://example.com",
        "third",
    ]
    assert [item["content"] for item in manager.search("TH", limit=1)] == ["third"]

    writes = []
    monkeypatch.setattr(manager, "set", lambda value: writes.append(value))
    monkeypatch.setattr(
        clipboard_module,
        "run_osascript",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
    )
    manager.paste("replacement")
    assert writes == ["replacement"]


def test_keyboard_simulator_failure_branches(monkeypatch):
    keyboard = KeyboardSimulator()
    monkeypatch.setattr(keyboard_module, "escape_applescript", lambda value: f"safe:{value}")
    monkeypatch.setattr(
        keyboard_module,
        "run_osascript",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=4),
    )
    assert keyboard.type_text("hello").success is False
    assert keyboard.press_key("return").success is False

    unsupported = keyboard.press_key("x", ["cmd", "bogus"])
    assert unsupported.success is False
    assert unsupported.error == "Unsupported keyboard modifier"

    monkeypatch.setattr(
        keyboard_module,
        "run_osascript",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("keyboard failed")),
    )
    assert keyboard.type_text("hello").error == "keyboard failed"
    assert keyboard.press_key("x").error == "keyboard failed"


def test_keyboard_simulator_script_variants(monkeypatch):
    keyboard = KeyboardSimulator()
    scripts = []
    monkeypatch.setattr(keyboard_module, "escape_applescript", lambda value: f"safe:{value}")
    monkeypatch.setattr(
        keyboard_module,
        "run_osascript",
        lambda script, **_kwargs: scripts.append(script) or SimpleNamespace(returncode=0),
    )

    assert keyboard.press_key("return", ["cmd", "shift"]).success
    assert keyboard.press_key("x", ["alt"]).success
    assert keyboard.press_key("tab").success
    assert keyboard.press_key("x").success
    assert any("key code 36 using" in script for script in scripts)
    assert any('keystroke "safe:x" using' in script for script in scripts)
    assert any("key code 48" in script for script in scripts)
