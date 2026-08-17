"""Sequence-based intent recognition."""

from __future__ import annotations

from typing import Optional

from phantom.models import IntentResult, IntentType, UserAction


class SequenceRecognizer:
    def __init__(self):
        self._history: list[UserAction] = []
        self._known: dict[str, IntentType] = {}

    def add_action(self, action: UserAction):
        self._history.append(action)
        if len(self._history) > 500:
            self._history = self._history[-500:]

    def recognize(self) -> Optional[IntentResult]:
        if len(self._history) < 3:
            return None

        recent = self._history[-8:]
        key = self._key(recent[:5])

        if key in self._known:
            return IntentResult(
                intent=self._known[key],
                confidence=0.75,
                context={"sequence_key": key},
            )

        # Detect repetition
        pattern = self._find_repeat(recent)
        if pattern:
            return IntentResult(
                intent=IntentType.UNKNOWN,
                confidence=0.60,
                context={"detected_pattern": pattern},
                suggested_automation={"type": "repeat", "steps": pattern},
            )
        return None

    def learn(self, key: str, intent: IntentType):
        self._known[key] = intent

    def _key(self, actions):
        return "|".join(f"{a.type.value}@{a.app_name}" for a in actions)

    def _find_repeat(self, actions):
        for length in range(2, min(5, len(actions) // 2 + 1)):
            p = self._key(actions[:length])
            count = sum(
                1
                for i in range(len(actions) - length + 1)
                if self._key(actions[i : i + length]) == p
            )
            if count >= 3:
                return [{"type": a.type.value, "app": a.app_name} for a in actions[:length]]
        return None
