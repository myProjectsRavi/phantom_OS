"""Trigger engine."""

from __future__ import annotations

import re
import time

from phantom.models import Recipe, TriggerEvent, TriggerType


class TriggerEngine:
    def __init__(self, library):
        self._library = library

    def check(self, event: TriggerEvent) -> list[Recipe]:
        event_type = event.type.value if hasattr(event.type, "value") else event.type
        matching = []
        for recipe in self._library.list_recipes():
            if not recipe.enabled or not recipe.trigger:
                continue
            if recipe.trigger.type != event_type:
                continue
            if self._evaluate(recipe.trigger, event):
                matching.append(recipe)
        return matching

    def _evaluate(self, trigger, event):
        t = trigger.type
        c = trigger.config
        d = event.data
        if t == TriggerType.APP_SWITCH.value:
            target = c.get("app", "")
            return d.get("app_name") == target if target else True
        elif t == TriggerType.CONTENT_MATCH.value:
            pattern = c.get("pattern", "")
            app_filter = c.get("app", "")
            if app_filter and d.get("app_name") != app_filter:
                return False
            return bool(re.search(pattern, d.get("text", "")))
        elif t == TriggerType.SCHEDULE.value:
            target = c.get("time", "")
            if not target:
                return False
            days = c.get("days", [])
            if days:
                today = time.strftime("%a").lower()
                if today not in [str(d).lower() for d in days]:
                    return False
            return time.strftime("%H:%M") == target
        elif t == TriggerType.IDLE.value:
            return d.get("idle_seconds", 0) >= c.get("seconds", 60)
        elif t == TriggerType.HOTKEY.value:
            return d.get("key") == c.get("key") and set(d.get("modifiers", [])) == set(
                c.get("modifiers", [])
            )
        elif t == TriggerType.PATTERN_MATCH.value:
            return d.get("pattern_id") == c.get("pattern_id")
        return False
