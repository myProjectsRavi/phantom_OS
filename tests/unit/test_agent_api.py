"""Coverage tests for the PhantomAgent public API."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from phantom.agent import PhantomAgent
from phantom.config import PhantomConfig
from phantom.events import PhantomEvents
from phantom.models import (
    ActionRequest,
    ActionResult,
    IntentResult,
    IntentType,
    LearnedPattern,
    PerceptionFrame,
    PhantomActionType,
    Recipe,
    RecipeStep,
    TriggerEvent,
    TriggerType,
    TrustLevel,
)


def _make_agent(tmp_path) -> PhantomAgent:
    config = PhantomConfig(
        recipe_dir=str(tmp_path / "recipes"),
        pattern_store=str(tmp_path / "patterns.json"),
        local_llm_helpers_enabled=False,
        neurovault_enabled=False,
    )
    return PhantomAgent(config=config)


def test_lifecycle_and_status(tmp_path):
    agent = _make_agent(tmp_path)
    seen_events = []
    agent.event_bus.on(PhantomEvents.DAEMON_STARTED, lambda _: seen_events.append("started"))
    agent.event_bus.on(PhantomEvents.DAEMON_STOPPED, lambda _: seen_events.append("stopped"))
    agent.start()
    assert agent.is_running is True
    assert agent.status["running"] is True
    assert agent.stats()["started_at"] > 0
    agent.pause()
    assert agent.is_running is False
    agent.resume()
    assert agent.is_running is True
    agent.stop()
    assert agent.is_running is False
    assert seen_events == ["started", "stopped"]


def test_perceive_intent_switch_and_patterns(tmp_path, monkeypatch):
    agent = _make_agent(tmp_path)
    frame_one = PerceptionFrame(app_name="Terminal", screen_type="terminal", window_title="run")
    frame_two = PerceptionFrame(app_name="Safari", screen_type="browser", window_title="search")
    frames = iter([frame_one, frame_two])
    monkeypatch.setattr(agent._perception, "perceive", lambda: next(frames))
    recorded = []; added = []; observed = []
    monkeypatch.setattr(agent._recorder, "record", lambda action: recorded.append(action))
    monkeypatch.setattr(agent._intent, "add_action", lambda action: added.append(action))
    monkeypatch.setattr(agent._prediction, "observe", lambda action: observed.append(action))
    monkeypatch.setattr(agent._intent, "recognize", lambda frame: IntentResult(intent=IntentType.CODING, confidence=0.9, source_app=frame.app_name))
    assert agent.perceive().app_name == "Terminal"
    assert agent.perceive().app_name == "Safari"
    intent = agent.current_intent()
    assert intent is not None and intent.intent == IntentType.CODING
    assert agent.get_active_app()["name"] == "Safari"
    assert agent.stats()["frames_processed"] == 2
    assert len(recorded) == len(added) == len(observed) == 1
    pattern = LearnedPattern(id="p1", name="switch", signature="switch->search")
    agent._patterns = {pattern.signature: pattern}
    events = []
    agent.event_bus.on(PhantomEvents.PATTERN_APPROVED, lambda payload: events.append(payload["id"]))
    agent.approve_pattern("p1")
    assert pattern.approved is True and events == ["p1"]


def test_execute_and_action_wrappers(tmp_path, monkeypatch):
    agent = _make_agent(tmp_path); captured = []
    async def _fake_execute(request):
        captured.append(request); return ActionResult(success=True, action_type=request.type)
    monkeypatch.setattr(agent._executor, "execute", _fake_execute)
    base = asyncio.run(agent.execute(ActionRequest(type=PhantomActionType.TYPE_TEXT, params={"text": "manual"}, source="test")))
    assert base.success is True
    assert agent.type_text("hello").success is True
    assert agent.activate_app("Safari").success is True
    assert agent.open_url("https://example.com").success is True
    assert [r.type for r in captured[-3:]] == [PhantomActionType.TYPE_TEXT, PhantomActionType.APP_ACTIVATE, PhantomActionType.URL_OPEN]
    assert agent.stats()["actions_executed"] >= 4


def test_sync_wrappers_inside_running_loop(tmp_path, monkeypatch):
    agent = _make_agent(tmp_path)
    async def _fake_execute(request): return ActionResult(success=True, action_type=request.type)
    monkeypatch.setattr(agent._executor, "execute", _fake_execute)
    async def _run(): return agent.type_text("inside-loop")
    result = asyncio.run(_run())
    assert result.success is True and result.action_type == PhantomActionType.TYPE_TEXT


def test_recipe_clipboard_and_safety_helpers(tmp_path, monkeypatch):
    agent = _make_agent(tmp_path)
    class _Clipboard:
        def __init__(self): self._value = ""
        def get(self): return self._value
        def set(self, value): self._value = value
        def history(self, limit=20): return [{"content": self._value}] * min(limit, 1)
    agent._executor._clipboard = _Clipboard(); agent._executor._history = [1, 2, 3]
    monkeypatch.setattr(agent._executor, "undo_last", lambda: ActionResult(success=True, action_type=PhantomActionType.WAIT))
    agent.clipboard_set("memo")
    assert agent.clipboard_get() == "memo"
    assert len(agent.clipboard_history(limit=1)) == 1
    assert agent.undo().success is True
    assert agent.action_history(limit=2) == [2, 3]
    monkeypatch.setattr(agent._triggers, "check", lambda _: [Recipe(name="match", source="builtin")])
    assert len(agent.matching_recipes(TriggerEvent(type=TriggerType.APP_SWITCH.value))) == 1
    assert "error" in asyncio.run(agent.run_recipe("missing"))
    recipe = Recipe(name="demo", steps=[RecipeStep(type="wait")], source="user")
    monkeypatch.setattr(agent._recipes, "get", lambda name: recipe if name == "demo" else None)
    async def _fake_run(_recipe, _variables): return {"success": True, "duration_ms": 4}
    monkeypatch.setattr(agent._runner, "run", _fake_run)
    stored = []
    agent._neurovault = SimpleNamespace(available=True, store_workflow=lambda name, steps: stored.append((name, steps)))
    assert asyncio.run(agent.run_recipe("demo"))["success"] is True
    assert stored == [("demo", ["wait"])]
    adds = []; saves = []
    monkeypatch.setattr(agent._recipes, "add", lambda rec: adds.append(rec.name)); monkeypatch.setattr(agent._recipes, "save", lambda rec: saves.append(rec.name))
    created = agent.create_recipe("local_recipe", [{"type": "wait", "params": {"seconds": 1}}])
    assert created.name == "local_recipe" and adds == ["local_recipe"] and saves == ["local_recipe"]
    toggle = Recipe(name="toggle", source="user", enabled=False)
    monkeypatch.setattr(agent._recipes, "get", lambda name: toggle if name == "toggle" else None)
    agent.enable_recipe("toggle"); assert toggle.enabled is True
    agent.disable_recipe("toggle"); assert toggle.enabled is False
    agent.set_trust_level(TrustLevel.APPROVE_EACH); assert agent.trust_level == TrustLevel.APPROVE_EACH
    agent.emergency_stop(); assert agent._safety.is_stopped is True
    assert "uptime_seconds" in agent.stats() and agent.frame_interval > 0
