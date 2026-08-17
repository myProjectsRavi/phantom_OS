"""Markov chain predictor."""

from __future__ import annotations

from collections import defaultdict

from phantom.models import ActionType, PredictedAction, UserAction


class MarkovPredictor:
    def __init__(self):
        self._transitions: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._totals: dict[str, int] = defaultdict(int)

    def observe(self, current: str, next_state: str):
        self._transitions[current][next_state] += 1
        self._totals[current] += 1

    def predict(self, current: str, top_k: int = 3) -> list[PredictedAction]:
        if current not in self._transitions:
            return []
        total = self._totals[current]
        if total == 0:
            return []
        predictions = []
        valid_action_values = {action.value for action in ActionType}
        for state, count in sorted(self._transitions[current].items(), key=lambda x: -x[1])[:top_k]:
            parts = state.split("@")
            at = ActionType(parts[0]) if parts[0] in valid_action_values else ActionType.UNKNOWN
            app = parts[1] if len(parts) > 1 else ""
            predictions.append(
                PredictedAction(
                    action_type=at, target_app=app, confidence=count / total, source="markov"
                )
            )
        return predictions

    @staticmethod
    def state_key(action: UserAction) -> str:
        return f"{action.type.value}@{action.app_name}"
