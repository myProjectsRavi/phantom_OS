"""Runtime coverage tests for ActionExecutor behavior."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from phantom.actions.executor import ActionExecutor
from phantom.events import EventBus, PhantomEvents
from phantom.models import ActionRequest, ActionResult, PhantomActionType


class _Safety:
    def __init__(self):
        self.allow_result = True
        self.approve_result = True
        self.require_approval = False
        self.success_count = 0
        self.error_count = 0

    def allow(self, _request):
        return self.allow_result

    def requires_approval(self, request):
        return self.require_approval or request.requires_approval

    async def request_approval(self, _request):
        return self.approve_result

    def record_success(self):
        self.success_count += 1

    def record_error(self):
        self.error_count += 1


def test_execute_blocked_and_rejected():
    safety = _Safety()
    safety.allow_result = False
    events = []
    bus = EventBus()
    bus.on(PhantomEvents.ACTION_BLOCKED, lambda payload: events.append(payload["type"]))

    executor = ActionExecutor(safety=safety, event_bus=bus)
    blocked = asyncio.run(
        executor.execute(ActionRequest(type=PhantomActionType.TYPE_TEXT, params={"text": "x"}))
    )
    assert blocked.success is False
    assert blocked.error == "Blocked by safety"
    assert events == ["type_text"]

    safety.allow_result = True
    safety.approve_result = False
    rejected = asyncio.run(
        executor.execute(
            ActionRequest(
                type=PhantomActionType.TYPE_TEXT,
                params={"text": "x"},
                requires_approval=True,
            )
        )
    )
    assert rejected.success is False
    assert rejected.error == "Rejected by user"


def test_execute_records_success_and_failure(monkeypatch):
    safety = _Safety()
    bus = EventBus()
    seen = {"executed": 0, "failed": 0}
    bus.on(
        PhantomEvents.ACTION_EXECUTED,
        lambda _payload: seen.__setitem__("executed", seen["executed"] + 1),
    )
    bus.on(
        PhantomEvents.ACTION_FAILED,
        lambda _payload: seen.__setitem__("failed", seen["failed"] + 1),
    )

    executor = ActionExecutor(safety=safety, event_bus=bus)
    monkeypatch.setattr(
        executor,
        "_dispatch",
        lambda request: ActionResult(success=True, action_type=request.type),
    )
    ok = asyncio.run(
        executor.execute(ActionRequest(type=PhantomActionType.NOTIFICATION, params={"title": "ok"}))
    )
    assert ok.success is True
    assert safety.success_count == 1

    monkeypatch.setattr(
        executor,
        "_dispatch",
        lambda request: ActionResult(success=False, action_type=request.type, error="boom"),
    )
    bad = asyncio.run(
        executor.execute(ActionRequest(type=PhantomActionType.NOTIFICATION, params={"title": "bad"}))
    )
    assert bad.success is False
    assert safety.error_count == 1
    assert seen == {"executed": 1, "failed": 1}
    assert len(executor._history) == 2


def test_dispatch_branches_and_helpers(monkeypatch):
    executor = ActionExecutor(safety=_Safety(), event_bus=EventBus())
    executor._keyboard = SimpleNamespace(
        type_text=lambda _text: ActionResult(success=True, action_type=PhantomActionType.TYPE_TEXT),
        press_key=lambda _key, _mods=None: ActionResult(
            success=True, action_type=PhantomActionType.PRESS_KEY
        ),
    )
    pasted = []
    set_values = []
    executor._clipboard = SimpleNamespace(
        copy=lambda: "clip",
        paste=lambda value=None: pasted.append(value),
        set=lambda value: set_values.append(value),
    )
    executor._app = SimpleNamespace(
        activate=lambda _app: ActionResult(success=True, action_type=PhantomActionType.APP_ACTIVATE),
        open_url=lambda _url: ActionResult(success=True, action_type=PhantomActionType.URL_OPEN),
        open_file=lambda _path: ActionResult(success=True, action_type=PhantomActionType.FILE_OPEN),
    )

    monkeypatch.setattr(
        "phantom.actions.executor.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="ok"),
    )
    sleeps = []
    monkeypatch.setattr("phantom.actions.executor.time.sleep", lambda value: sleeps.append(value))
    monkeypatch.setattr("phantom.actions.executor.platform.system", lambda: "Darwin")
    monkeypatch.setattr(
        "phantom.actions.executor.run_osascript",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=""),
    )

    assert executor._dispatch(ActionRequest(type=PhantomActionType.TYPE_TEXT)).success
    assert executor._dispatch(ActionRequest(type=PhantomActionType.PRESS_KEY)).success
    copied = executor._dispatch(ActionRequest(type=PhantomActionType.CLIPBOARD_COPY))
    assert copied.metadata["content"] == "clip"
    assert executor._dispatch(
        ActionRequest(type=PhantomActionType.CLIPBOARD_PASTE, params={"content": "x"})
    ).success
    assert executor._dispatch(
        ActionRequest(type=PhantomActionType.CLIPBOARD_SET, params={"content": "y"})
    ).success
    assert pasted == ["x"]
    assert set_values == ["y"]
    assert executor._dispatch(ActionRequest(type=PhantomActionType.APP_ACTIVATE)).success
    assert executor._dispatch(ActionRequest(type=PhantomActionType.URL_OPEN)).success
    assert executor._dispatch(ActionRequest(type=PhantomActionType.FILE_OPEN)).success
    assert executor._dispatch(
        ActionRequest(type=PhantomActionType.RUN_COMMAND, params={"command": ["echo", "ok"]})
    ).success
    assert executor._dispatch(ActionRequest(type=PhantomActionType.WAIT, params={"seconds": 0.1})).success
    assert executor._dispatch(
        ActionRequest(
            type=PhantomActionType.NOTIFICATION,
            params={"title": "Hi", "message": "There"},
        )
    ).success
    assert executor._dispatch(ActionRequest(type=PhantomActionType.SEQUENCE)).success is False
    assert executor._dispatch(ActionRequest(type=PhantomActionType.MOUSE_CLICK)).success is False

    assert executor._parse_command(["echo", "x"]) == ["echo", "x"]
    assert executor._parse_command("echo hi") == ["echo", "hi"]
    assert executor._parse_command("echo hi; rm -rf /") == []
    assert executor._parse_command(12) == []
    assert sleeps


def test_sequence_reenters_execute(monkeypatch):
    safety = _Safety()
    executor = ActionExecutor(safety=safety, event_bus=EventBus())
    seen = []
    monkeypatch.setattr(
        executor,
        "_dispatch",
        lambda request: seen.append(request.type)
        or ActionResult(success=True, action_type=request.type),
    )
    result = asyncio.run(
        executor.execute(
            ActionRequest(
                type=PhantomActionType.SEQUENCE,
                params={"steps": [{"type": "wait", "params": {"seconds": 0}}]},
            )
        )
    )
    assert result.success is True
    assert seen == [PhantomActionType.WAIT]
    assert len(executor._history) == 2


def test_undo_uses_safety_path(monkeypatch):
    safety = _Safety()
    executor = ActionExecutor(safety=safety, event_bus=EventBus())
    monkeypatch.setattr(
        executor,
        "_dispatch",
        lambda request: ActionResult(success=True, action_type=request.type),
    )
    executor._history = [
        ActionResult(
            success=True,
            action_type=PhantomActionType.TYPE_TEXT,
            undo_info={"type": "wait", "params": {"seconds": 0}},
        )
    ]
    undone = executor.undo_last()
    assert undone is not None
    assert undone.action_type == PhantomActionType.WAIT

    executor._history = []
    assert executor.undo_last() is None
