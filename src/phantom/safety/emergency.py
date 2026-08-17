"""Emergency stop handler."""

from __future__ import annotations

import logging
import time

from phantom.applescript import notification_script, run_osascript
from phantom.safety.policy import SafetyPolicy

logger = logging.getLogger(__name__)


class EmergencyStop:
    def __init__(self, safety: SafetyPolicy):
        self._safety = safety
        self._times: list[float] = []

    def on_key(self, key: str):
        if key != "escape":
            self._times = []
            return
        now = time.time()
        self._times.append(now)
        self._times = [t for t in self._times if now - t < 0.5]
        if len(self._times) >= 3:
            self._safety.emergency_stop()
            self._times = []
            try:
                run_osascript(
                    notification_script("PHANTOM Emergency Stop", "All actions stopped"),
                    timeout=3,
                )
            except OSError as exc:
                logger.debug("Failed to show emergency stop notification: %s", exc)
            except Exception as exc:
                logger.warning("Unexpected error showing emergency stop notification: %s", exc)
