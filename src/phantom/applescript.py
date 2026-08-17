"""Helpers for safe AppleScript execution."""

from __future__ import annotations

import subprocess


def escape_applescript(value: str) -> str:
    """Escape a value for safe interpolation inside AppleScript string literals."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def run_osascript(
    script: str,
    *,
    timeout: int = 5,
    capture_output: bool = False,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["osascript", "-e", script],
        timeout=timeout,
        capture_output=capture_output,
        text=True,
        check=False,
    )


def notification_script(title: str, message: str) -> str:
    safe_title = escape_applescript(title)
    safe_message = escape_applescript(message)
    return f'display notification "{safe_message}" with title "{safe_title}"'


ACTIVE_APP_SCRIPT = """
tell application "System Events"
    set frontApp to name of first application process whose frontmost is true
    set frontBundle to bundle identifier of first application process whose frontmost is true
    tell (first application process whose frontmost is true)
        try
            set winTitle to name of front window
        on error
            set winTitle to ""
        end try
    end tell
end tell
return frontApp & "|" & frontBundle & "|" & winTitle
"""


def read_active_app_info() -> tuple[str, str, str]:
    result = run_osascript(ACTIVE_APP_SCRIPT, timeout=3, capture_output=True)
    parts = (result.stdout or "").strip().split("|")
    app_name = parts[0] if parts and parts[0] else "Unknown"
    bundle = parts[1] if len(parts) > 1 else ""
    title = parts[2] if len(parts) > 2 else ""
    return app_name, bundle, title
