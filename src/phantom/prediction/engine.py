"""Prediction engine orchestrator."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Optional

from phantom.models import PredictedAction, UserAction
from phantom.prediction.app_context import AppContextPredictor
from phantom.prediction.markov import MarkovPredictor
from phantom.prediction.time_patterns import TimePredictor


class PredictionEngine:
    def __init__(self):
        self._markov = MarkovPredictor()
        self._time = TimePredictor()
        self._app = AppContextPredictor()
        self._last: Optional[UserAction] = None
        self._app_start = time.time()
        self._current_app = ""

    def observe(self, action: UserAction):
        if self._last:
            self._markov.observe(
                MarkovPredictor.state_key(self._last), MarkovPredictor.state_key(action)
            )
        self._time.observe(action)
        if action.app_name != self._current_app:
            dur = time.time() - self._app_start
            if self._current_app:
                self._app.observe(self._current_app, action.app_name, dur)
            self._current_app = action.app_name
            self._app_start = time.time()
        self._last = action

    def predict(self) -> list[PredictedAction]:
        all_preds = []
        if self._last:
            all_preds.extend(self._markov.predict(MarkovPredictor.state_key(self._last)))
        all_preds.extend(self._time.predict())
        all_preds.extend(self._app.predict(self._current_app, time.time() - self._app_start))
        return self._aggregate(all_preds)

    def _aggregate(self, predictions):
        by_key = defaultdict(list)
        for p in predictions:
            by_key[f"{p.action_type.value}@{p.target_app}"].append(p)
        result = []
        for key, preds in by_key.items():
            best = max(preds, key=lambda p: p.confidence)
            if len(preds) > 1:
                best.confidence = min(1.0, best.confidence * 1.2)
            result.append(best)
        return sorted(result, key=lambda p: -p.confidence)[:5]
