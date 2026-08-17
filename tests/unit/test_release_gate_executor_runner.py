"""Release-gate coverage for executor and recipe runner branches."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import phantom.actions.executor as executor_module
import phantom.automation.runner as runner_module
from phantom.actions.executor import ActionExecutor
from phantom.automation.runner import RecipeRunner
from phantom.events import EventBus
from phantom.models import (
    ActionRequest,
    ActionResult,
    PhantomActionType,
    Recipe,
    RecipeStep,
)


class _AllowSafety:
    def __init__(self):
        self.success = 0
        self.errors = 0

    def allow(self, _request):
        return True

    def requires_approval(self, _request):
        return False

    async def request_approval(self, _request):
        return True

    def record_success(self):
        self.success += 1

    def record_error(self):
        self.errors += 1


class _RunnerExecutor:
    def __init__(self, results):
        self.clipboard = SimpleNamespace(get=lambda: "initial")
        self.results = list(results)
        self.requests = []

    async def execute(self, request):
        self.requests.append(request)
        if not self.results:
            return ActionResult(success=True, action_type=request.type)
        return self.results.pop(0)


def test_executor_notification_platform_branches(monkeypatch):
    executor = ActionExecutor(safety=_AllowSafety(), event_bus=EventBus())
    request = ActionRequest(
        type=PhantomActionType.NOTIFICATION,
        params={"title": "Title", "message": "Body"},
    )

    monkeypatch.setattr(executor_module.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        executor_module, "notification_script", lambda title, body: f"{title}:{body}"
    )
    monkeypatch.setattr(
        executor_module,
        "run_osascript",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=5),
    )
    result = executor._dispatch(request)
    assert result.success is False and "Notification failed with 5" in result.error

    monkeypatch.setattr(
        executor_module,
        "run_osascript",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
    )
    assert executor._dispatch(request).success is True

    monkeypatch.setattr(executor_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        executor_module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=6),
    )
    result = executor._dispatch(request)
    assert result.success is False and "Notification failed with 6" in result.error

    monkeypatch.setattr(
        executor_module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
    )
    assert executor._dispatch(request).success is True

    monkeypatch.setattr(executor_module.platform, "system", lambda: "Windows")
    assert executor._dispatch(request).success is True


def test_executor_dispatch_exception_and_command_failure(monkeypatch):
    executor = ActionExecutor(safety=_AllowSafety(), event_bus=EventBus())
    monkeypatch.setattr(
        executor_module.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("subprocess failed")),
    )
    request = ActionRequest(
        type=PhantomActionType.RUN_COMMAND,
        params={"command": ["echo", "hello"]},
    )
    assert executor._dispatch(request).error == "subprocess failed"

    monkeypatch.setattr(
        executor_module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=9, stdout="partial"),
    )
    result = executor._dispatch(request)
    assert result.success is False
    assert result.error == "Command exited with 9"
    assert result.metadata == {"stdout": "partial", "returncode": 9}


def test_executor_sequence_invalid_shapes_and_child_failure(monkeypatch):
    executor = ActionExecutor(safety=_AllowSafety(), event_bus=EventBus())

    invalid_list = asyncio.run(
        executor._exec_sequence(
            ActionRequest(type=PhantomActionType.SEQUENCE, params={"steps": "bad"})
        )
    )
    assert invalid_list.error == "Invalid sequence steps"

    invalid_step = asyncio.run(
        executor._exec_sequence(
            ActionRequest(type=PhantomActionType.SEQUENCE, params={"steps": ["bad"]})
        )
    )
    assert invalid_step.error == "Invalid sequence step"

    invalid_type = asyncio.run(
        executor._exec_sequence(
            ActionRequest(
                type=PhantomActionType.SEQUENCE,
                params={"steps": [{"type": "not-a-real-action"}]},
            )
        )
    )
    assert invalid_type.error.startswith("Invalid sequence step:")

    async def fail_child(_request):
        return ActionResult(
            success=False,
            action_type=PhantomActionType.WAIT,
            error="child failed",
        )

    monkeypatch.setattr(executor, "execute", fail_child)
    failed = asyncio.run(
        executor._exec_sequence(
            ActionRequest(
                type=PhantomActionType.SEQUENCE,
                params={"steps": [{"type": "wait", "params": {"seconds": 0}}]},
            )
        )
    )
    assert failed.error == "child failed"


def test_executor_sequence_delay_and_approval_flag(monkeypatch):
    executor = ActionExecutor(safety=_AllowSafety(), event_bus=EventBus())
    seen = []
    sleeps = []

    async def success_child(request):
        seen.append(request)
        return ActionResult(success=True, action_type=request.type)

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(executor, "execute", success_child)
    monkeypatch.setattr(executor_module.asyncio, "sleep", fake_sleep)
    result = asyncio.run(
        executor._exec_sequence(
            ActionRequest(
                type=PhantomActionType.SEQUENCE,
                source="parent",
                params={
                    "steps": [
                        {
                            "type": "wait",
                            "params": {"seconds": 0},
                            "requires_approval": True,
                            "delay_after": 0.25,
                        }
                    ]
                },
            )
        )
    )
    assert result.success is True
    assert seen[0].requires_approval is True
    assert seen[0].source == "parent"
    assert sleeps == [0.25]


def test_executor_parse_command_edge_cases():
    executor = ActionExecutor(safety=_AllowSafety(), event_bus=EventBus())
    assert executor._parse_command(None) == []
    assert executor._parse_command(123) == []
    assert executor._parse_command("") == []
    assert executor._parse_command("echo one && echo two") == []
    assert executor._parse_command("echo $(date)") == []
    assert executor._parse_command("echo 'unterminated") == []
    assert executor._parse_command(["echo", "", "value"]) == ["echo", "value"]


def test_executor_undo_invalid_metadata_and_active_loop():
    executor = ActionExecutor(safety=_AllowSafety(), event_bus=EventBus())
    executor._history = [
        ActionResult(
            success=True,
            action_type=PhantomActionType.TYPE_TEXT,
            undo_info={"params": {}},
        )
    ]
    result = asyncio.run(executor.undo_last_async())
    assert result is not None
    assert result.success is False
    assert result.error == "Invalid undo metadata"

    async def call_sync_undo_inside_loop():
        with pytest.raises(RuntimeError, match="await undo_last_async"):
            executor.undo_last()

    asyncio.run(call_sync_undo_inside_loop())


def test_executor_history_is_bounded(monkeypatch):
    safety = _AllowSafety()
    executor = ActionExecutor(safety=safety, event_bus=EventBus())
    executor._history = [
        ActionResult(success=True, action_type=PhantomActionType.WAIT) for _ in range(1000)
    ]
    monkeypatch.setattr(
        executor,
        "_dispatch",
        lambda request: ActionResult(success=True, action_type=request.type),
    )
    result = asyncio.run(
        executor.execute(ActionRequest(type=PhantomActionType.WAIT, params={"seconds": 0}))
    )
    assert result.success is True
    assert len(executor._history) == 1000
    assert safety.success == 1


def test_runner_invalid_condition_and_unknown_action():
    executor = _RunnerExecutor([])
    runner = RecipeRunner(executor, EventBus())

    invalid_condition = Recipe(
        name="bad-condition",
        steps=[RecipeStep(type="wait", condition="len(items) > 0")],
    )
    result = asyncio.run(runner.run(invalid_condition, {"items": [1]}))
    assert result["success"] is False
    assert result["step"] == 0
    assert "Invalid recipe condition" in result["error"]

    unknown = Recipe(name="bad-action", steps=[RecipeStep(type="does-not-exist")])
    result = asyncio.run(runner.run(unknown))
    assert result["success"] is False
    assert result["error"] == "Unknown recipe action type: does-not-exist"


def test_runner_clipboard_updates_retry_and_continue(monkeypatch):
    results = [
        ActionResult(
            success=True,
            action_type=PhantomActionType.CLIPBOARD_COPY,
            metadata={"content": "copied"},
        ),
        ActionResult(success=True, action_type=PhantomActionType.CLIPBOARD_SET),
        ActionResult(success=False, action_type=PhantomActionType.WAIT, error="first"),
        ActionResult(success=False, action_type=PhantomActionType.WAIT, error="second"),
    ]
    executor = _RunnerExecutor(results)
    runner = RecipeRunner(executor, EventBus())
    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(runner_module.asyncio, "sleep", fake_sleep)
    recipe = Recipe(
        name="clipboard-flow",
        steps=[
            RecipeStep(type="clipboard_copy"),
            RecipeStep(type="clipboard_set", params={"content": "{clipboard}-next"}),
            RecipeStep(type="wait", max_retries=2, on_error="continue", delay_after=0.2),
            RecipeStep(type="notification", params={"message": "{clipboard}"}),
        ],
    )
    result = asyncio.run(runner.run(recipe))
    assert result["success"] is False
    assert sleeps == [0.2]
    assert executor.requests[1].params["content"] == "copied-next"
    assert executor.requests[-1].params["message"] == "copied-next"


def test_runner_condition_evaluator_all_supported_operators():
    runner = RecipeRunner(_RunnerExecutor([]), EventBus())
    values = {"a": 2, "b": 3, "items": [2, 4], "flag": False}

    assert runner._condition_true("True", values) is True
    assert runner._condition_true("a != b", values) is True
    assert runner._condition_true("a < b", values) is True
    assert runner._condition_true("a <= 2", values) is True
    assert runner._condition_true("b > a", values) is True
    assert runner._condition_true("b >= 3", values) is True
    assert runner._condition_true("a in items", values) is True
    assert runner._condition_true("b not in items", values) is True
    assert runner._condition_true("not flag", values) is True
    assert runner._condition_true("a == 2 or b == 0", values) is True
    assert runner._condition_true("a == 2 and b == 3", values) is True
    assert runner._condition_true("a == b == 3", values) is False

    with pytest.raises(ValueError, match="Unsupported condition expression"):
        runner._condition_true("a + b", values)
