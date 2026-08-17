"""Release-gate coverage for remaining PhantomAgent state and persistence branches."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

import phantom.agent as agent_module
import phantom.llm as llm_package
from phantom.agent import PhantomAgent
from phantom.config import PhantomConfig
from phantom.models import (
    ActionRequest,
    ActionResult,
    IntentResult,
    IntentType,
    LearnedPattern,
    PerceptionFrame,
    PhantomActionType,
    Recipe,
)


def _agent(tmp_path):
    return PhantomAgent(
        PhantomConfig(
            recipe_dir=str(tmp_path / "recipes"),
            pattern_store=str(tmp_path / "patterns.json"),
            local_llm_helpers_enabled=False,
            neurovault_enabled=False,
        )
    )


def test_class_constructors_and_empty_state(tmp_path, monkeypatch):
    config = PhantomConfig(
        recipe_dir=str(tmp_path / "recipes"),
        pattern_store=str(tmp_path / "patterns.json"),
        local_llm_helpers_enabled=False,
        neurovault_enabled=False,
    )
    monkeypatch.setattr(agent_module.PhantomConfig, "load", classmethod(lambda cls, _path=None: config))

    from_init = PhantomAgent.init(tmp_path / "config.toml")
    from_open = PhantomAgent.open()
    assert isinstance(from_init, PhantomAgent)
    assert isinstance(from_open, PhantomAgent)
    assert from_init.get_active_app() is None
    assert from_init.current_intent() is None


def test_status_reports_current_state_and_optional_integrations(tmp_path, monkeypatch):
    agent = _agent(tmp_path)
    agent._running = True
    agent._last_frame = PerceptionFrame(app_name="Code")
    agent._last_intent = IntentResult(intent=IntentType.CODING, confidence=0.8)
    agent._patterns = {"x": LearnedPattern(signature="x")}
    agent._neurovault = SimpleNamespace(available=True)
    agent._local_llm_helpers = SimpleNamespace(available=True)
    monkeypatch.setattr(agent, "_get_llm_provider_name", lambda: "mock")

    status = agent.status
    assert status["running"] is True
    assert status["current_app"] == "Code"
    assert status["current_intent"] == "coding"
    assert status["patterns"] == 1
    assert status["neurovault"] is True
    assert status["local_llm_helpers"] is True
    assert status["llm_provider"] == "mock"


def test_perceive_none_and_discover_pattern_early_return(tmp_path, monkeypatch):
    agent = _agent(tmp_path)
    monkeypatch.setattr(agent._perception, "perceive", lambda: None)
    assert agent.perceive() is None
    monkeypatch.setattr(agent._recorder, "get_recent", lambda _limit: [object()] * 9)
    assert agent.discover_patterns() == []


def test_discover_patterns_adds_only_new_and_stores_neurovault(tmp_path, monkeypatch):
    agent = _agent(tmp_path)
    existing = LearnedPattern(name="existing", signature="same", frequency=2)
    fresh = LearnedPattern(
        name="fresh",
        signature="new",
        frequency=4,
        confidence=0.7,
        steps=[{"type": "wait"}],
    )
    agent._patterns = {existing.signature: existing}
    monkeypatch.setattr(agent._recorder, "get_recent", lambda _limit: [object()] * 10)
    monkeypatch.setattr(agent._discovery, "analyze", lambda _actions: [existing, fresh])
    stored = []
    agent._neurovault = SimpleNamespace(
        available=True,
        store_pattern=lambda name, payload: stored.append((name, payload)),
    )
    saved = []
    monkeypatch.setattr(agent, "_save_patterns", lambda: saved.append(True))

    result = agent.discover_patterns()

    assert result == [existing, fresh]
    assert agent._patterns["new"] is fresh
    assert agent._stats["patterns_discovered"] == 1
    assert stored[0][0] == "fresh"
    assert stored[0][1]["signature"] == "new"
    assert saved == [True]


def test_discover_patterns_without_changes_does_not_save(tmp_path, monkeypatch):
    agent = _agent(tmp_path)
    existing = LearnedPattern(name="existing", signature="same")
    agent._patterns = {"same": existing}
    monkeypatch.setattr(agent._recorder, "get_recent", lambda _limit: [object()] * 10)
    monkeypatch.setattr(agent._discovery, "analyze", lambda _actions: [existing])
    monkeypatch.setattr(agent, "_save_patterns", lambda: pytest.fail("unexpected save"))
    assert agent.discover_patterns() == [existing]


def test_pattern_loader_skips_bad_entries_and_supports_dict_payload(tmp_path, monkeypatch):
    agent = _agent(tmp_path)
    path = Path(agent.config.pattern_store)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "patterns": [
                    "not-a-dict",
                    {"id": "empty", "signature": ""},
                    {"id": "good", "name": "Good", "signature": "sig", "tags": [1, "x"]},
                ]
            }
        )
    )
    agent._patterns = {}
    monkeypatch.setattr(agent_module.logger, "info", lambda *_args, **_kwargs: None)
    agent._load_patterns()
    assert list(agent._patterns) == ["sig"]
    assert agent._patterns["sig"].tags == ["1", "x"]


def test_pattern_loader_invalid_payload_and_save_failure_are_nonfatal(tmp_path, monkeypatch):
    agent = _agent(tmp_path)
    path = Path(agent.config.pattern_store)
    path.write_text("42")
    agent._patterns = {}
    agent._load_patterns()
    assert agent._patterns == {}

    agent._patterns = {"x": LearnedPattern(signature="x")}
    warnings = []
    monkeypatch.setattr(agent_module.logger, "warning", lambda *args, **_kwargs: warnings.append(args))
    monkeypatch.setattr(
        agent_module.tempfile,
        "mkstemp",
        lambda **_kwargs: (_ for _ in ()).throw(OSError("no temp")),
    )
    agent._save_patterns()
    assert warnings


def test_pattern_serialization_round_trip_all_fields():
    pattern = LearnedPattern(
        id="p",
        name="name",
        signature="sig",
        steps=[{"type": "wait"}],
        frequency=5,
        confidence=0.9,
        last_seen=10.0,
        created_at=5.0,
        approved=True,
        auto_execute=True,
        tags=["a"],
    )
    payload = PhantomAgent._serialize_pattern(pattern)
    restored = PhantomAgent._deserialize_pattern(payload)
    assert restored == pattern


def test_failed_action_does_not_increment_counter(tmp_path, monkeypatch):
    agent = _agent(tmp_path)

    async def fail(request):
        return ActionResult(success=False, action_type=request.type, error="blocked")

    monkeypatch.setattr(agent._executor, "execute", fail)
    before = agent._stats["actions_executed"]
    result = asyncio.run(agent.execute(ActionRequest(type=PhantomActionType.WAIT)))
    assert result.success is False
    assert agent._stats["actions_executed"] == before


def test_run_async_propagates_error_inside_existing_loop():
    async def outer():
        async def boom():
            raise ValueError("async failed")

        with pytest.raises(ValueError, match="async failed"):
            PhantomAgent._run_async(boom())

    asyncio.run(outer())


def test_recipe_toggle_missing_and_non_neurovault_success(tmp_path, monkeypatch):
    agent = _agent(tmp_path)
    assert agent.list_recipes() == agent._recipes.list_recipes()

    monkeypatch.setattr(agent._recipes, "get", lambda _name: None)
    agent.enable_recipe("missing")
    agent.disable_recipe("missing")

    recipe = Recipe(name="demo", source="user")
    monkeypatch.setattr(agent._recipes, "get", lambda name: recipe if name == "demo" else None)

    async def run_ok(_recipe, _variables):
        return {"success": True}

    monkeypatch.setattr(agent._runner, "run", run_ok)
    agent._neurovault = None
    before = agent._stats["recipes_run"]
    assert asyncio.run(agent.run_recipe("demo"))["success"] is True
    assert agent._stats["recipes_run"] == before + 1


def test_integration_properties_and_llm_provider_name(tmp_path, monkeypatch):
    agent = _agent(tmp_path)
    nv = SimpleNamespace(available=False)
    helpers = SimpleNamespace(available=False)
    agent._neurovault = nv
    agent._local_llm_helpers = helpers
    assert agent.neurovault is nv
    assert agent.local_llm_helpers is helpers

    available = SimpleNamespace(available=lambda: True, name="mock")
    monkeypatch.setattr(llm_package, "get_provider", lambda _config: available)
    assert agent.llm is available
    assert agent._get_llm_provider_name() == "mock"

    unavailable = SimpleNamespace(available=lambda: False, name="mock")
    monkeypatch.setattr(llm_package, "get_provider", lambda _config: unavailable)
    assert agent._get_llm_provider_name() == "none"

    monkeypatch.setattr(
        llm_package,
        "get_provider",
        lambda _config: (_ for _ in ()).throw(RuntimeError("provider error")),
    )
    assert agent._get_llm_provider_name() == "none"


def test_stats_without_start_and_logging_setup(tmp_path):
    agent = _agent(tmp_path)
    agent._stats["started_at"] = 0.0
    assert agent.stats()["uptime_seconds"] == 0

    agent.config.log_level = "not-a-real-level"
    agent._setup_logging()
    logger = logging.getLogger("phantom")
    assert logger.level == logging.INFO
    assert len(logger.handlers) == 2
    assert logger.propagate is False
