"""Tests for AppleScript helper usage in action modules."""

from types import SimpleNamespace

from phantom.actions.app_control import AppController
from phantom.actions.clipboard import ClipboardManager


def test_clipboard_copy_and_paste_use_applescript_helper(monkeypatch):
    calls = []

    def _fake_run(script: str, *, timeout: int = 5, capture_output: bool = False):
        calls.append((script, timeout, capture_output))
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr("phantom.actions.clipboard.run_osascript", _fake_run)

    manager = ClipboardManager()
    monkeypatch.setattr(manager, "get", lambda: "copied-text")

    assert manager.copy() == "copied-text"
    manager.paste()

    assert calls[0][0] == 'tell application "System Events" to keystroke "c" using command down'
    assert calls[1][0] == 'tell application "System Events" to keystroke "v" using command down'


def test_list_running_uses_applescript_helper(monkeypatch):
    def _fake_run(script: str, *, timeout: int = 5, capture_output: bool = False):
        assert "name of every application process" in script
        assert timeout == 5
        assert capture_output is True
        return SimpleNamespace(returncode=0, stdout="Safari, Terminal,")

    monkeypatch.setattr("phantom.actions.app_control.run_osascript", _fake_run)

    controller = AppController()
    assert controller.list_running() == ["Safari", "Terminal"]
