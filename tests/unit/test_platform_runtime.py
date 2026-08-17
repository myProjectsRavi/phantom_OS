"""Runtime tests for platform adapters."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import phantom.actions.platform as platform_mod
from phantom.actions.platform import LinuxAdapter, MacOSAdapter, create_platform_adapter


def test_factory_uses_runtime_platform(monkeypatch):
    monkeypatch.setattr(platform_mod.platform, "system", lambda: "Linux")
    adapter = create_platform_adapter()
    assert isinstance(adapter, LinuxAdapter)


def test_macos_adapter_runtime_paths(monkeypatch):
    monkeypatch.setattr(
        platform_mod,
        "read_active_app_info",
        lambda: ("Safari", "com.apple.Safari", "Docs"),
    )
    monkeypatch.setattr(platform_mod, "escape_applescript", lambda value: f"safe:{value}")
    scripts = []
    monkeypatch.setattr(
        platform_mod,
        "run_osascript",
        lambda script, timeout=5, capture_output=False: scripts.append(
            (script, timeout, capture_output)
        ),
    )
    monkeypatch.setattr(
        platform_mod, "notification_script", lambda title, message: f"{title}:{message}"
    )

    def _run(cmd, **_kwargs):
        if cmd[0] == "pbpaste":
            return SimpleNamespace(stdout="clipboard-data")
        if cmd[0] == "osascript":
            return SimpleNamespace(stdout="Safari, Terminal,")
        raise AssertionError(f"unexpected command: {cmd}")

    writes = []

    class _Proc:
        def communicate(self, payload):
            writes.append(payload.decode("utf-8"))

    monkeypatch.setattr(platform_mod.subprocess, "run", _run)
    monkeypatch.setattr(platform_mod.subprocess, "Popen", lambda *_a, **_k: _Proc())

    class _FakeMSS:
        monitors = [None, "monitor-1"]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

        def grab(self, monitor):
            return {"monitor": monitor}

    monkeypatch.setitem(sys.modules, "mss", SimpleNamespace(mss=lambda: _FakeMSS()))
    monkeypatch.setattr(platform_mod, "np", SimpleNamespace(array=lambda value: ("array", value)))

    adapter = MacOSAdapter()
    active = adapter.get_active_app()
    assert active.name == "Safari"
    assert active.bundle_id == "com.apple.Safari"
    assert adapter.get_clipboard() == "clipboard-data"

    adapter.set_clipboard("hello")
    assert writes == ["hello"]

    adapter.type_text("hello")
    adapter.press_key("return", ["cmd", "shift"])
    adapter.press_key("x")
    adapter.activate_app("Safari")
    shot = adapter.screenshot()
    adapter.show_notification("Hi", "There")
    apps = adapter.list_running_apps()

    assert shot == ("array", {"monitor": "monitor-1"})
    assert apps == ["Safari", "Terminal"]
    assert any("safe:hello" in script for script, *_ in scripts)
    assert any("safe:return" in script for script, *_ in scripts)
    assert any("safe:Safari" in script for script, *_ in scripts)


def test_linux_adapter_runtime_paths(monkeypatch):
    def _run(cmd, **_kwargs):
        if cmd[:3] == ["xdotool", "getactivewindow", "getwindowclassname"]:
            return SimpleNamespace(stdout="Terminal\n")
        if cmd[:3] == ["xdotool", "getactivewindow", "getwindowname"]:
            return SimpleNamespace(stdout="Build logs\n")
        if cmd[:3] == ["xclip", "-selection", "clipboard"]:
            return SimpleNamespace(stdout="linux-clip")
        if cmd[:2] == ["wmctrl", "-l"]:
            return SimpleNamespace(
                stdout="0x1  0 host desktop Terminal\n0x2  0 host desktop Browser\n"
            )
        return SimpleNamespace(stdout="")

    writes = []

    class _Proc:
        def communicate(self, payload):
            writes.append(payload.decode("utf-8"))

    monkeypatch.setattr(platform_mod.subprocess, "run", _run)
    monkeypatch.setattr(platform_mod.subprocess, "Popen", lambda *_a, **_k: _Proc())

    class _FakeMSS:
        monitors = [None, "linux-monitor"]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

        def grab(self, monitor):
            return {"monitor": monitor}

    monkeypatch.setitem(sys.modules, "mss", SimpleNamespace(mss=lambda: _FakeMSS()))
    monkeypatch.setattr(platform_mod, "np", SimpleNamespace(array=lambda value: ("array", value)))

    adapter = LinuxAdapter()
    active = adapter.get_active_app()
    assert active.name == "Terminal"
    assert active.window_title == "Build logs"
    assert adapter.get_clipboard() == "linux-clip"

    adapter.set_clipboard("world")
    assert writes == ["world"]

    adapter.type_text("abc")
    adapter.press_key("x", ["ctrl"])
    adapter.activate_app("Terminal")
    screenshot = adapter.screenshot()
    adapter.show_notification("Title", "Message")
    apps = adapter.list_running_apps()

    assert screenshot == ("array", {"monitor": "linux-monitor"})
    assert apps == ["Browser", "Terminal"]


def test_linux_and_macos_screenshot_requires_numpy(monkeypatch):
    monkeypatch.setattr(platform_mod, "np", None)
    monkeypatch.setitem(sys.modules, "mss", SimpleNamespace(mss=lambda: None))

    with pytest.raises(RuntimeError):
        MacOSAdapter().screenshot()

    with pytest.raises(RuntimeError):
        LinuxAdapter().screenshot()
