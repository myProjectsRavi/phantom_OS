"""Pattern discovery engine."""

from __future__ import annotations

from collections import defaultdict

from phantom.models import LearnedPattern, UserAction


class PatternDiscovery:
    MIN_LENGTH = 2
    MAX_LENGTH = 12
    MIN_FREQ = 3

    def __init__(self):
        self._candidates: dict[str, dict] = {}

    def analyze(self, actions: list[UserAction]) -> list[LearnedPattern]:
        signatures: dict[str, int] = defaultdict(int)
        for length in range(self.MIN_LENGTH, min(self.MAX_LENGTH + 1, len(actions) // 2 + 1)):
            for start in range(len(actions) - length + 1):
                window = actions[start : start + length]
                sig = "|".join(f"{a.type.value}@{a.app_name}" for a in window)
                signatures[sig] += 1
                if sig not in self._candidates:
                    self._candidates[sig] = {
                        "steps": [
                            {"type": a.type.value, "app": a.app_name, "data": a.data}
                            for a in window
                        ],
                        "first_seen": window[0].timestamp,
                    }
        patterns = []
        for sig, count in signatures.items():
            if count >= self.MIN_FREQ:
                confidence = min(1.0, count / 5.0)
                if confidence >= 0.60:
                    info = self._candidates.get(sig, {})
                    apps = list(dict.fromkeys(s["app"] for s in info.get("steps", [])))
                    patterns.append(
                        LearnedPattern(
                            name="_".join(apps[:2]),
                            signature=sig,
                            steps=info.get("steps", []),
                            frequency=count,
                            confidence=confidence,
                            last_seen=actions[-1].timestamp if actions else 0,
                        )
                    )
        return self._deduplicate(sorted(patterns, key=lambda p: -p.confidence))

    def _deduplicate(self, patterns):
        seen = set()
        result = []
        for p in patterns:
            if not any(p.signature in s for s in seen):
                result.append(p)
                seen.add(p.signature)
        return result
