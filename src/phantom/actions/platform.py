"""Cross-platform abstractions for UI automation primitives."""

from __future__ import annotations

import platform
import subprocess
from abc import ABC, abstractmethod
from typing import Any, NoReturn

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]

from phantom.applescript import (
    escape_applescript,
    notification_script,
    read_active_app_info,
    run_osascript,
)
from phantom.models import AppInfo


class PlatformAdapter(ABC):
    """Abstract platform-specific operations."""

    @abstractmethod
    def get_active_app(self) -> AppInfo: ...

    @abstractmethod
    def get_clipboard(self) -> str: ...

    @abstractmethod
    def set_clipboard(self, content: str): ...

    @abstractmethod
    def type_text(self, text: str): ...

    @abstractmethod
    def press_key(self, key: str, modifiers: list[str] | None = None): ...

    @abstractmethod
    def activate_app(self, app_name: str): ...

    @abstractmethod
    def screenshot(self) -> Any: ...

    @abstractmethod
    def show_notification(self, title: str, message: str): ...

    @abstractmethod
    def list_running_apps(self) -> list[str]: ...


class MacOSAdapter(PlatformAdapter):
    """macOS implementation using osascript and native utilities."""

    def get_active_app(self) -> AppInfo:
        app_name, bundle_id, window_title = read_active_app_info()
        return AppInfo(
            name=app_name,
            bundle_id=bundle_id,
            window_title=window_title,
        )

    def get_clipboard(self) -> str:
        return subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=2).stdout

    def set_clipboard(self, content: str):
        proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        proc.communicate(content.encode("utf-8"))

    def type_text(self, text: str):
        escaped = escape_applescript(text)
        run_osascript(
            f'tell application "System Events" to keystroke "{escaped}"',
            timeout=10,
        )

    def press_key(self, key: str, modifiers: list[str] | None = None):
        if modifiers:
            mod_map = {
                "cmd": "command down",
                "ctrl": "control down",
                "alt": "option down",
                "shift": "shift down",
            }
            mods = ", ".join(mod_map.get(m, m) for m in modifiers)
            safe_key = escape_applescript(key)
            script = f'tell application "System Events" to keystroke "{safe_key}" using {{{mods}}}'
        else:
            safe_key = escape_applescript(key)
            script = f'tell application "System Events" to keystroke "{safe_key}"'
        run_osascript(script, timeout=5)

    def activate_app(self, app_name: str):
        safe_app = escape_applescript(app_name)
        run_osascript(f'tell application "{safe_app}" to activate', timeout=5)

    def screenshot(self) -> Any:
        import mss

        if np is None:  # pragma: no cover
            raise RuntimeError("numpy is required for screenshot capture")
        with mss.mss() as sct:
            return np.array(sct.grab(sct.monitors[1]))

    def show_notification(self, title: str, message: str):
        run_osascript(notification_script(title, message), timeout=3)

    def list_running_apps(self) -> list[str]:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to get name of every application process whose background only is false',
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return [item.strip() for item in result.stdout.split(",") if item.strip()]


class LinuxAdapter(PlatformAdapter):
    """Linux implementation using xdotool/xclip/wmctrl."""

    def get_active_app(self) -> AppInfo:
        name = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowclassname"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        title = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        return AppInfo(name=name, bundle_id="", window_title=title)

    def get_clipboard(self) -> str:
        return subprocess.run(
            ["xclip", "-selection", "clipboard", "-o"],
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout

    def set_clipboard(self, content: str):
        proc = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
        proc.communicate(content.encode("utf-8"))

    def type_text(self, text: str):
        subprocess.run(["xdotool", "type", "--clearmodifiers", text], timeout=10)

    def press_key(self, key: str, modifiers: list[str] | None = None):
        combo = "+".join((modifiers or []) + [key])
        subprocess.run(["xdotool", "key", combo], timeout=5)

    def activate_app(self, app_name: str):
        subprocess.run(["wmctrl", "-a", app_name], timeout=5)

    def screenshot(self) -> Any:
        import mss

        if np is None:  # pragma: no cover
            raise RuntimeError("numpy is required for screenshot capture")
        with mss.mss() as sct:
            return np.array(sct.grab(sct.monitors[1]))

    def show_notification(self, title: str, message: str):
        subprocess.run(["notify-send", title, message], timeout=3)

    def list_running_apps(self) -> list[str]:
        result = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True)
        names = []
        for line in result.stdout.strip().splitlines():
            parts = line.split(None, 4)
            if len(parts) >= 5:
                names.append(parts[4].strip())
        return sorted(set(names))


class UnsupportedPlatformAdapter(PlatformAdapter):
    """Fallback adapter for unsupported platforms."""

    def _unsupported(self, op: str) -> NoReturn:
        raise RuntimeError(f"Platform operation not supported for {op}")

    def get_active_app(self) -> AppInfo:  # pragma: no cover
        self._unsupported("get_active_app")

    def get_clipboard(self) -> str:  # pragma: no cover
        self._unsupported("get_clipboard")

    def set_clipboard(self, content: str):  # pragma: no cover
        del content
        self._unsupported("set_clipboard")

    def type_text(self, text: str):  # pragma: no cover
        del text
        self._unsupported("type_text")

    def press_key(self, key: str, modifiers: list[str] | None = None):  # pragma: no cover
        del key, modifiers
        self._unsupported("press_key")

    def activate_app(self, app_name: str):  # pragma: no cover
        del app_name
        self._unsupported("activate_app")

    def screenshot(self) -> Any:  # pragma: no cover
        self._unsupported("screenshot")

    def show_notification(self, title: str, message: str):  # pragma: no cover
        del title, message
        self._unsupported("show_notification")

    def list_running_apps(self) -> list[str]:  # pragma: no cover
        self._unsupported("list_running_apps")


def create_platform_adapter(system: str | None = None) -> PlatformAdapter:
    current = (system or platform.system()).lower()
    if current == "darwin":
        return MacOSAdapter()
    if current == "linux":
        return LinuxAdapter()
    return UnsupportedPlatformAdapter()
