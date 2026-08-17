"""Event bus for PHANTOM observability."""

from __future__ import annotations

import logging
from collections import defaultdict


class PhantomEvents:
    FRAME_CAPTURED = "frame.captured"
    FRAME_PROCESSED = "frame.processed"
    INTENT_DETECTED = "intent.detected"
    PATTERN_DISCOVERED = "pattern.discovered"
    PATTERN_APPROVED = "pattern.approved"
    PREDICTION_MADE = "prediction.made"
    ACTION_REQUESTED = "action.requested"
    ACTION_EXECUTED = "action.executed"
    ACTION_FAILED = "action.failed"
    ACTION_BLOCKED = "action.blocked"
    RECIPE_TRIGGERED = "recipe.triggered"
    RECIPE_COMPLETED = "recipe.completed"
    RECIPE_FAILED = "recipe.failed"
    TRIGGER_FIRED = "trigger.fired"
    SAFETY_BLOCKED = "safety.blocked"
    EMERGENCY_STOP = "emergency.stop"
    APP_SWITCHED = "app.switched"
    CLIPBOARD_CHANGED = "clipboard.changed"
    TRUST_CHANGED = "trust.changed"
    DAEMON_STARTED = "daemon.started"
    DAEMON_STOPPED = "daemon.stopped"


class EventBus:
    def __init__(self):
        self._handlers = defaultdict(list)
        self._logger = logging.getLogger("phantom.events")

    def on(self, event, handler):
        self._handlers[event].append(handler)

    def emit(self, event, data=None):
        for handler in self._handlers.get(event, []):
            try:
                handler(data or {})
            except Exception as e:
                self._logger.warning("Event handler error [%s]: %s", event, e)
        self._logger.debug("Event: %s", event)

    def off(self, event, handler=None):
        if handler:
            self._handlers[event] = [h for h in self._handlers[event] if h != handler]
        else:
            self._handlers[event] = []
