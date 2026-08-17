"""Smart clipboard manager."""

from __future__ import annotations

import subprocess
import time

from phantom.applescript import run_osascript


class ClipboardManager:
    def __init__(self, max_history=100):
        self._history: list[dict] = []
        self._max = max_history

    def copy(self) -> str:
        completed = run_osascript(
            'tell application "System Events" to keystroke "c" using command down',
            timeout=3,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"clipboard copy shortcut failed with {completed.returncode}")
        time.sleep(0.1)
        return self.get()

    def paste(self, content=None):
        if content is not None:
            self.set(content)
        completed = run_osascript(
            'tell application "System Events" to keystroke "v" using command down',
            timeout=3,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"clipboard paste shortcut failed with {completed.returncode}")

    def get(self) -> str:
        completed = subprocess.run(
            ["pbpaste"], capture_output=True, text=True, timeout=2, check=False
        )
        if completed.returncode != 0:
            raise RuntimeError(f"pbpaste exited with {completed.returncode}")
        return completed.stdout

    def set(self, content: str):
        proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        proc.communicate(content.encode("utf-8"))
        if proc.returncode != 0:
            raise RuntimeError(f"pbcopy exited with {proc.returncode}")
        self._add(content)

    def search(self, query: str, limit=5):
        needle = query.lower()
        return [item for item in reversed(self._history) if needle in item["content"].lower()][
            :limit
        ]

    def history(self, limit=20):
        return self._history[-limit:]

    def _add(self, content):
        self._history.append(
            {
                "content": content,
                "timestamp": time.time(),
                "type": self._classify(content),
            }
        )
        if len(self._history) > self._max:
            self._history = self._history[-self._max :]

    def _classify(self, content):
        if content.startswith(("http://", "https://")):
            return "url"
        if any(keyword in content for keyword in ["def ", "class ", "function "]):
            return "code"
        if "@" in content and "." in content:
            return "email"
        return "text"
