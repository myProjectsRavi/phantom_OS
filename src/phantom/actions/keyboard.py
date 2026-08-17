"""Keyboard simulation."""

from __future__ import annotations

from phantom.applescript import escape_applescript, run_osascript
from phantom.models import ActionResult, PhantomActionType


class KeyboardSimulator:
    KEY_CODES = {
        "return": 36,
        "tab": 48,
        "space": 49,
        "delete": 51,
        "escape": 53,
        "up": 126,
        "down": 125,
        "left": 123,
        "right": 124,
    }

    def type_text(self, text: str) -> ActionResult:
        try:
            escaped = escape_applescript(text)
            completed = run_osascript(
                f'tell application "System Events" to keystroke "{escaped}"',
                timeout=10,
            )
            if completed.returncode != 0:
                return ActionResult(
                    success=False,
                    action_type=PhantomActionType.TYPE_TEXT,
                    error=f"osascript exited with {completed.returncode}",
                )
            return ActionResult(success=True, action_type=PhantomActionType.TYPE_TEXT)
        except Exception as exc:
            return ActionResult(
                success=False, action_type=PhantomActionType.TYPE_TEXT, error=str(exc)
            )

    def press_key(self, key: str, modifiers: list[str] | None = None) -> ActionResult:
        try:
            if modifiers:
                mod_map = {
                    "cmd": "command down",
                    "ctrl": "control down",
                    "alt": "option down",
                    "shift": "shift down",
                }
                mapped = [mod_map[m] for m in modifiers if m in mod_map]
                if len(mapped) != len(modifiers):
                    return ActionResult(
                        success=False,
                        action_type=PhantomActionType.PRESS_KEY,
                        error="Unsupported keyboard modifier",
                    )
                mods = ", ".join(mapped)
                if key in self.KEY_CODES:
                    script = f'tell application "System Events" to key code {self.KEY_CODES[key]} using {{{mods}}}'
                else:
                    safe_key = escape_applescript(key)
                    script = f'tell application "System Events" to keystroke "{safe_key}" using {{{mods}}}'
            else:
                if key in self.KEY_CODES:
                    script = f'tell application "System Events" to key code {self.KEY_CODES[key]}'
                else:
                    safe_key = escape_applescript(key)
                    script = f'tell application "System Events" to keystroke "{safe_key}"'
            completed = run_osascript(script, timeout=5)
            if completed.returncode != 0:
                return ActionResult(
                    success=False,
                    action_type=PhantomActionType.PRESS_KEY,
                    error=f"osascript exited with {completed.returncode}",
                )
            return ActionResult(success=True, action_type=PhantomActionType.PRESS_KEY)
        except Exception as exc:
            return ActionResult(
                success=False, action_type=PhantomActionType.PRESS_KEY, error=str(exc)
            )
