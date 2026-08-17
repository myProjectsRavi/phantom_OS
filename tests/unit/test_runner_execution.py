"""Execution-path tests for RecipeRunner."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from phantom.automation.runner import RecipeRunner
from phantom.events import EventBus, PhantomEvents
from phantom.models import ActionResult, PhantomActionType, Recipe, RecipeStep


class _Executor:
    def __init__(self, results):
        self.clipboard = SimpleNamespace(get=lambda: "clip-content")
        self._results = list(results)
        self.requests = []

    async def execute(self, request):
        self.requests.append(request)
        return self._results.pop(0)


def test_runner_run_with_skip_retry_and_completion(monkeypatch):
    recipe = Recipe(
        name="flow",
        variables={"name": "world"},
        steps=[
            RecipeStep(type="wait", params={"seconds": 0}, condition="app == 'Code'"),
            RecipeStep(type="wait", params={"seconds": 0}, max_retries=2, on_error="continue"),
            RecipeStep(
                type="notification",
                params={"title": "Hello {name}", "message": "{clipboard}"},
                delay_after=0.1,
            ),
        ],
    )

    executor = _Executor(
        [
            ActionResult(success=False, action_type=PhantomActionType.WAIT, error="retry"),
            ActionResult(success=True, action_type=PhantomActionType.WAIT, duration_ms=3),
            ActionResult(success=True, action_type=PhantomActionType.NOTIFICATION, duration_ms=5),
        ]
    )
    bus = EventBus()
    seen = {"triggered": 0, "completed": 0}
    bus.on(
        PhantomEvents.RECIPE_TRIGGERED,
        lambda _p: seen.__setitem__("triggered", seen["triggered"] + 1),
    )
    bus.on(
        PhantomEvents.RECIPE_COMPLETED,
        lambda _p: seen.__setitem__("completed", seen["completed"] + 1),
    )

    sleeps = []

    async def _sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr("phantom.automation.runner.asyncio.sleep", _sleep)

    runner = RecipeRunner(executor, bus)
    result = asyncio.run(runner.run(recipe, variables={"app": "Terminal"}))

    assert result["success"] is True
    assert result["results"][0]["skipped"] is True
    assert result["results"][1]["success"] is True
    assert recipe.run_count == 1
    assert recipe.last_run is not None
    assert recipe.success_rate == 1.0
    assert seen == {"triggered": 1, "completed": 1}
    assert sleeps == [0.1]

    request = executor.requests[-1]
    assert request.params["title"] == "Hello world"
    assert request.params["message"] == "clip-content"


def test_runner_abort_on_error_and_condition_helpers():
    recipe = Recipe(
        name="abort",
        steps=[RecipeStep(type="wait", params={"seconds": 0}, on_error="abort")],
    )
    executor = _Executor(
        [ActionResult(success=False, action_type=PhantomActionType.WAIT, error="boom")]
    )
    bus = EventBus()
    failed = []
    bus.on(PhantomEvents.RECIPE_FAILED, lambda payload: failed.append(payload["step"]))
    runner = RecipeRunner(executor, bus)

    result = asyncio.run(runner.run(recipe))
    assert result["success"] is False
    assert result["step"] == 0
    assert failed == [0]

    interpolated = runner._interpolate({"title": "Hi {name}"}, {"name": "dev"})
    assert interpolated["title"] == "Hi dev"
    assert runner._condition_true(
        "not blocked and app in allowed", {"blocked": False, "app": "Code", "allowed": ["Code"]}
    )
