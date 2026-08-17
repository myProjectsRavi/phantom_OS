"""Coverage tests for public PhantomOS integration bridges."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from phantom.integrations import local_llm_bridge, neurovault_bridge
from phantom.models import IntentResult, IntentType, PerceptionFrame


def test_neurovault_bridge_unavailable(monkeypatch):
    monkeypatch.setattr(neurovault_bridge, "HAS_NEUROVAULT", False)
    bridge = neurovault_bridge.NeurovaultBridge("phantom-test")

    assert bridge.available is False
    assert bridge.store_pattern("p", {"confidence": 0.5}) is None
    assert bridge.enrich_intent("Terminal", "Error") == {}
    assert bridge.search_patterns("x") == []
    assert bridge.store_workflow("w", ["a"]) is None


def test_neurovault_bridge_retries_open_after_exists_error(monkeypatch):
    calls = {"open": 0}

    class _Vault:
        pass

    class _NeurovaultEngine:
        @classmethod
        def open(cls, *_args, **_kwargs):
            calls["open"] += 1
            if calls["open"] < 3:
                raise RuntimeError("open failed")
            return _Vault()

        @classmethod
        def init(cls, *_args, **_kwargs):
            raise RuntimeError("already exists")

    monkeypatch.setattr(neurovault_bridge, "HAS_NEUROVAULT", True)
    monkeypatch.setattr(neurovault_bridge, "NeurovaultEngine", _NeurovaultEngine, raising=False)
    bridge = neurovault_bridge.NeurovaultBridge("phantom-test", base_dir="/tmp/phantom")
    assert bridge.available is True
    assert calls["open"] >= 3


def test_neurovault_bridge_methods_handle_errors(monkeypatch):
    class _Vault:
        def ingest(self, **_kwargs):
            raise RuntimeError("boom")

        def recall(self, **_kwargs):
            raise RuntimeError("boom")

    class _NeurovaultEngine:
        @classmethod
        def open(cls, *_args, **_kwargs):
            return _Vault()

        @classmethod
        def init(cls, *_args, **_kwargs):
            return _Vault()

    monkeypatch.setattr(neurovault_bridge, "HAS_NEUROVAULT", True)
    monkeypatch.setattr(neurovault_bridge, "NeurovaultEngine", _NeurovaultEngine, raising=False)
    bridge = neurovault_bridge.NeurovaultBridge("phantom-test")

    assert bridge.store_pattern("p", {"confidence": 0.1}) is None
    assert bridge.enrich_intent("App", "text") == {}
    assert bridge.search_patterns("x") == []
    assert bridge.store_workflow("w", ["a"]) is None


def test_neurovault_bridge_operational(monkeypatch):
    class _Vault:
        def __init__(self):
            self.ingested = []

        def ingest(self, **kwargs):
            self.ingested.append(kwargs)
            return f"ingest:{kwargs['source']}"

        def recall(self, **_kwargs):
            return [
                SimpleNamespace(memory=SimpleNamespace(content="Pattern A")),
                SimpleNamespace(content="Pattern B"),
            ]

    class _NeurovaultEngine:
        @classmethod
        def open(cls, *_args, **_kwargs):
            return _Vault()

        @classmethod
        def init(cls, *_args, **_kwargs):
            raise AssertionError("init should not be used when open succeeds")

    monkeypatch.setattr(neurovault_bridge, "HAS_NEUROVAULT", True)
    monkeypatch.setattr(neurovault_bridge, "NeurovaultEngine", _NeurovaultEngine, raising=False)

    bridge = neurovault_bridge.NeurovaultBridge("phantom-test")
    assert bridge.available is True
    assert bridge.store_pattern("daily", {"confidence": 0.8}) == "ingest:phantom.pattern"

    enriched = bridge.enrich_intent("Terminal", "Exception occurred")
    assert enriched["related_patterns"] == ["Pattern A", "Pattern B"]
    assert bridge.search_patterns("pattern", limit=2)
    assert bridge.store_workflow("morning", ["a", "b"]) == "ingest:phantom.workflow"


def _attach_mock_provider(bridge):
    class _MockProvider:
        def available(self):
            return True

        @property
        def name(self):
            return "mock"

        async def complete(self, prompt, system="", temperature=0.3, max_tokens=1024):
            return SimpleNamespace(content="test response")

    bridge._provider = _MockProvider()


def test_local_llm_bridge_fallback(monkeypatch):
    monkeypatch.setattr(local_llm_bridge.LocalLLMBridge, "_init", lambda self: None)
    bridge = local_llm_bridge.LocalLLMBridge()
    assert bridge.available is False

    _attach_mock_provider(bridge)
    assert bridge.available is True
    result = asyncio.run(bridge._complete("test"))
    assert result.content == "test response"


def test_local_llm_bridge_async_flows(monkeypatch):
    monkeypatch.setattr(local_llm_bridge.LocalLLMBridge, "_init", lambda self: None)
    bridge = local_llm_bridge.LocalLLMBridge()

    responses = iter(
        [
            "coding",
            '{"name":"auto","description":"desc","trigger":{"type":"hotkey","config":{"key":"r"}},"steps":[{"type":"wait","params":{"seconds":1},"delay_after":0.0}]}',
            '{"type":"notification","params":{"title":"Hi"}}',
        ]
    )

    class _Provider:
        async def complete(self, *_args, **_kwargs):
            return SimpleNamespace(content=next(responses))

    bridge._provider = _Provider()
    frame = PerceptionFrame(app_name="Code", screen_type="editor", window_title="main.py")
    candidates = [
        IntentResult(intent=IntentType.CODING, confidence=0.4),
        IntentResult(intent=IntentType.WRITING, confidence=0.3),
    ]

    chosen = asyncio.run(bridge.disambiguate_intent(frame, candidates))
    assert chosen.intent == IntentType.CODING
    assert chosen.confidence > 0.4

    recipe = asyncio.run(bridge.generate_recipe("make a quick helper"))
    assert recipe.name == "auto"
    assert len(recipe.steps) == 1

    suggested = asyncio.run(bridge.suggest_action(frame, candidates[0]))
    assert suggested is not None
    assert suggested.type.value == "notification"
    assert suggested.source == "local_llm"


def test_local_llm_parse_json_from_fenced_block():
    payload = """```json
{"type":"notification","params":{"title":"hello"}}
```"""
    parsed = local_llm_bridge.LocalLLMBridge._parse_json(payload)
    assert parsed["type"] == "notification"
