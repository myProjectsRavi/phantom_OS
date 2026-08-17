"""App context predictor."""

from __future__ import annotations

from collections import defaultdict

from phantom.models import ActionType, PredictedAction


class AppContextPredictor:
    def __init__(self):
        self._transitions: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._durations: dict[str, list[float]] = defaultdict(list)

    def observe(self, from_app: str, to_app: str, duration: float):
        self._transitions[from_app][to_app] += 1
        self._durations[from_app].append(duration)
        if len(self._durations[from_app]) > 100:
            self._durations[from_app] = self._durations[from_app][-100:]

    def predict(self, current_app: str, time_in_app: float) -> list[PredictedAction]:
        transitions = self._transitions.get(current_app, {})
        if not transitions:
            return []
        total = sum(transitions.values())
        durations = self._durations.get(current_app, [60])
        avg_dur = sum(durations) / max(len(durations), 1)
        remaining = max(0, avg_dur - time_in_app)
        return [
            PredictedAction(
                action_type=ActionType.APP_SWITCH,
                target_app=app,
                confidence=count / total,
                expected_in_seconds=remaining,
                source="app_context",
                preparation={"type": "preload", "app": app},
            )
            for app, count in sorted(transitions.items(), key=lambda x: -x[1])[:3]
        ]
