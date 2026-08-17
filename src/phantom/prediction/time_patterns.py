"""Time-of-day predictor."""

from __future__ import annotations

import time
from collections import defaultdict

from phantom.models import ActionType, PredictedAction, UserAction


class TimePredictor:
    def __init__(self):
        self._patterns: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def observe(self, action: UserAction):
        hour = int(time.strftime("%H", time.localtime(action.timestamp)))
        bucket = hour // 2
        state = f"{action.type.value}@{action.app_name}"
        self._patterns[bucket][state] += 1

    def predict(self, top_k: int = 3) -> list[PredictedAction]:
        bucket = int(time.strftime("%H")) // 2
        states = self._patterns.get(bucket, {})
        if not states:
            return []
        total = sum(states.values())
        results = []
        valid_action_values = {action.value for action in ActionType}
        for state, count in sorted(states.items(), key=lambda x: -x[1])[:top_k]:
            parts = state.split("@")
            at = ActionType(parts[0]) if parts[0] in valid_action_values else ActionType.UNKNOWN
            results.append(PredictedAction(action_type=at, target_app=parts[1] if len(parts) > 1 else "", confidence=count / total, source="time_pattern"))
        return results
