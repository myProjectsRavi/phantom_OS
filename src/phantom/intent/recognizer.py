"""Intent recognizer orchestrator."""

from __future__ import annotations

from phantom.intent.rules import RuleBasedRecognizer
from phantom.intent.sequences import SequenceRecognizer
from phantom.models import IntentResult, IntentType, PerceptionFrame


class IntentRecognizer:
    def __init__(self):
        self._rules = RuleBasedRecognizer()
        self._sequences = SequenceRecognizer()
        self._buffer: list[PerceptionFrame] = []

    def recognize(self, frame: PerceptionFrame) -> IntentResult:
        self._buffer.append(frame)
        if len(self._buffer) > 30:
            self._buffer = self._buffer[-30:]

        # Tier 1: Rules
        result = self._rules.recognize(self._buffer)
        if result and result.confidence > 0.80:
            return result

        # Tier 2: Sequences
        seq = self._sequences.recognize()
        if seq and seq.confidence > 0.70:
            return seq

        # Tier 1 fallback
        if result and result.confidence > 0.50:
            return result

        # Default
        if frame.is_typing:
            return IntentResult(
                intent=IntentType.WRITING, confidence=0.55, source_app=frame.app_name
            )
        if frame.idle_seconds > 30:
            return IntentResult(intent=IntentType.IDLE, confidence=0.95)

        return IntentResult(intent=IntentType.BROWSING, confidence=0.40, source_app=frame.app_name)

    def add_action(self, action):
        self._sequences.add_action(action)
