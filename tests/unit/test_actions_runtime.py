"""Runtime coverage tests for action and AppleScript modules."""

from __future__ import annotations

from types import SimpleNamespace

from phantom.actions.app_control import AppController
from phantom.actions.clipboard import ClipboardManager
from phantom.actions.keyboard import KeyboardSimulator
from phantom.applescript import (
    escape_applescript,
    notification_script,
    read_active_app_info,
    run_osascript,
)
from phantom.models import PhantomActionType


def test_keyboard_simulator_success_and_error(monkeypatch):
    calls = []

    def _ok(script, timeout=5, capture_output=False):
        calls.append((script, timeout, capture_output))
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr("phantom.actions.keyboard.run_osascript", _ok)
    keyboard = KeyboardSimulator()

    assert keyboard.type_text('hello "world"').success is True
    assert keyboard.press_key("return", ["cmd", "shift"]).success is True
    assert keyboard.press_key("x").success is True
    assert "key code" in calls[1][0]
    assert calls[2][0].endswith('keystroke "x"')
    assert keyboard.press_key("x", ["invented"]).success is False

    monkeypatch.setattr(
        "phantom.actions.keyboard.run_osascript",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout=""),
    )
    assert keyboard.type_text("x").success is False
    assert keyboard.press_key("x").success is False


def test_clipboard_manager_paths(monkeypatch):
    scripts = []

    def _script(script, timeout=5, capture_output=False):
        scripts.append((script, timeout, capture_output))
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr("phantom.actions.clipboard.run_osascript", _script)
    monkeypatch.setattr("phantom.actions.clipboard.time.sleep", lambda _seconds: None)
    monkeypatch.setattr(
        "phantom.actions.clipboard.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="from-paste"),
    )

    writes = []

    class _Proc:
        returncode = 0

        def communicate(self, payload):
            writes.append(payload.decode("utf-8"))

    monkeypatch.setattr("phantom.actions.clipboard.subprocess.Popen", lambda *_a, **_k: _Proc())

    clipboard = ClipboardManager(max_history=2)
    assert clipboard.copy() == "from-paste"
    clipboard.paste("hello")
    clipboard.paste()
    clipboard.set("person@example.test")
    clipboard.set("def fn(): pass")
    clipboard.set("https://example.com")

    assert scripts[0][0].endswith('keystroke "c" using command down')
    assert scripts[1][0].endswith('keystroke "v" using command down')
    assert clipboard.get() == "from-paste"
    assert len(clipboard.history(limit=10)) == 2
    assert clipboard.search("https")
    assert clipboard._classify("https://example.com") == "url"
    assert clipboard._classify("def x(): pass") == "code"
    assert clipboard._classify("person@example.test") == "email"
    assert clipboard._classify("plain text") == "text"
    assert writes


def test_clipboard_native_failure_is_propagated(monkeypatch):
    monkeypatch.setattr(
        "phantom.actions.clipboard.run_osascript",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout=""),
    )
    clipboard = ClipboardManager()
    try:
        clipboard.copy()
    except RuntimeError as exc:
        assert "failed" in str(exc)
    else:
        raise AssertionError("clipboard copy failure must propagate")


def test_app_controller_paths(monkeypatch):
    monkeypatch.setattr("phantom.actions.app_control.escape_applescript", lambda value: value)
    monkeypatch.setattr(
        "phantom.actions.app_control.run_osascript",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="Safari, Terminal,"),
    )
    monkeypatch.setattr(
        "phantom.actions.app_control.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=""),
    )

    controller = AppController()
    assert controller.activate("Safari").success is True
    assert controller.open_url("https://example.com").success is True
    assert controller.open_url("javascript:alert(1)").success is False
    assert controller.open_url("file:///tmp/demo.txt").success is False
    assert controller.open_url("example.com/path").success is False
    assert controller.open_file("/tmp/demo.txt").success is True
    assert controller.list_running() == ["Safari", "Terminal"]

    monkeypatch.setattr(
        "phantom.actions.app_control.run_osascript",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout=""),
    )
    assert controller.activate("Safari").success is False

    monkeypatch.setattr(
        "phantom.actions.app_control.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout=""),
    )
    assert controller.open_url("https://example.com").success is False
    assert controller.open_file("/tmp/demo.txt").success is False


def test_applescript_helpers(monkeypatch):
    calls = []

    def _fake_run(argv, timeout, capture_output, text, check):
        calls.append((argv, timeout, capture_output, text, check))
        return SimpleNamespace(returncode=0, stdout="Terminal|com.apple.Terminal|Build")

    monkeypatch.setattr("phantom.applescript.subprocess.run", _fake_run)

    escaped = escape_applescript('a"b\\c')
    assert '\\"' in escaped
    assert "\\\\" in escaped

    result = run_osascript('display dialog "ok"', timeout=3, capture_output=True)
    assert result.stdout.startswith("Terminal|")
    assert calls[0][0][:2] == ["osascript", "-e"]

    note = notification_script("Hi", "There")
    assert 'with title "Hi"' in note

    app, bundle, title = read_active_app_info()
    assert app == "Terminal"
    assert bundle == "com.apple.Terminal"
    assert title == "Build"

    monkeypatch.setattr(
        "phantom.applescript.run_osascript",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=""),
    )
    assert read_active_app_info()[0] == "Unknown"
    assert PhantomActionType.TYPE_TEXT.value == "type_text"
