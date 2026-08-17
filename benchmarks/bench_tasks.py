"""Reproducible microbenchmarks for the current PhantomOS runtime."""

from __future__ import annotations

from phantom.automation.triggers import TriggerEngine
from phantom.intent.recognizer import IntentRecognizer
from phantom.models import (
    ActionRequest,
    PerceptionFrame,
    PhantomActionType,
    Recipe,
    RecipeTrigger,
    TriggerEvent,
)
from phantom.safety.policy import SafetyPolicy


class _Library:
    def __init__(self, recipes):
        self._recipes = recipes

    def list_recipes(self):
        return self._recipes


def test_safety_policy_allow_latency(benchmark):
    """Measure the hot-path cost of authorizing a benign action."""
    policy = SafetyPolicy(max_actions_per_minute=100_000)
    request = ActionRequest(
        type=PhantomActionType.URL_OPEN,
        params={"url": "https://github.com/myProjectsRavi/phantom_OS"},
        source="benchmark",
    )

    benchmark(policy.allow, request)


def test_trigger_matching_latency(benchmark):
    """Measure trigger matching across 1,000 recipes."""
    recipes = [
        Recipe(
            name=f"recipe-{index}",
            trigger=RecipeTrigger(type="app_switch", config={"app": f"App-{index}"}),
        )
        for index in range(1000)
    ]
    recipes.append(
        Recipe(
            name="match",
            trigger=RecipeTrigger(type="app_switch", config={"app": "Code"}),
        )
    )
    engine = TriggerEngine(_Library(recipes))
    event = TriggerEvent(type="app_switch", data={"app_name": "Code"})

    matches = benchmark(engine.check, event)
    assert [item.name for item in matches] == ["match"]


def test_intent_recognition_latency(benchmark):
    """Measure rule-based intent recognition for a representative coding frame."""
    recognizer = IntentRecognizer()
    frame = PerceptionFrame(
        app_name="Code",
        window_title="phantomOS — executor.py",
        screen_type="editor",
        text_content={"main": "def execute(request):\n    return result"},
    )

    result = benchmark(recognizer.recognize, frame)
    assert result is not None


def test_sequence_blocklist_walk_latency(benchmark):
    """Measure recursive safety inspection of a 100-step sequence."""
    policy = SafetyPolicy(max_actions_per_minute=100_000)
    request = ActionRequest(
        type=PhantomActionType.SEQUENCE,
        source="benchmark",
        params={"steps": [{"type": "wait", "params": {"seconds": 0}} for _ in range(100)]},
    )

    assert benchmark(policy.allow, request) is True
