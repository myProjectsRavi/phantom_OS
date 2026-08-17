"""Action recorder."""

from __future__ import annotations

import time
from typing import Callable

from phantom.models import UserAction


class ActionRecorder:
    def __init__(self, max_actions: int = 10000):
        self._actions: list[UserAction] = []
        self._max = max_actions
        self._listeners: list[Callable[[UserAction], None]] = []

    def record(self, action: UserAction):
        self._actions.append(action)
        if len(self._actions) > self._max:
            self._actions = self._actions[-self._max :]
        for listener in self._listeners:
            try:
                listener(action)
            except Exception:
                pass

    def get_recent(self, count=50):
        return self._actions[-count:]

    def get_window(self, seconds=300):
        cutoff = time.time() - seconds
        return [a for a in self._actions if a.timestamp >= cutoff]

    def on_action(self, listener: Callable[[UserAction], None]):
        self._listeners.append(listener)
