"""Release-gate coverage for LLM routing and safety fail-closed behavior."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import phantom.llm as llm_package
import phantom.llm.router as router
from phantom.config import PhantomConfig
from phantom.integrations.local_llm_bridge import LocalLLMBridge
from phantom.llm.provider import NullProvider
from phantom.models import (
    ActionRequest,
    IntentResult,
    IntentType,
    PerceptionFrame,
    PhantomActionType,
    TrustLevel,
)
from phantom.safety.policy import SafetyPolicy


class _Provider:
    def __init__(self, *, available=True, content="coding", name="provider"):
        self._available = available
        self.content = content
        self.name = name
        self.calls = []

    def available(self):
        return self._available

    async def complete(self, prompt, system="", temperature=0.3, max_tokens=1024):
        self.calls.append((prompt, system, temperature, max_tokens))
        return SimpleNamespace(content=self.content)


def test_local_llm_init_available_unavailable_and_exception(monkeypatch):
    available = _Provider(available=True)
    monkeypatch.setattr(llm_package, "get_provider", lambda _config: available)
    bridge = LocalLLMBridge(config=SimpleNamespace())
    assert bridge.available is True
    assert bridge._provider is available

    unavailable = _Provider(available=False)
    monkeypatch.setattr(llm_package, "get_provider", lambda _config: unavailable)
    bridge = LocalLLMBridge(config=SimpleNamespace())
    assert bridge.available is False

    monkeypatch.setattr(
        llm_package,
        "get_provider",
        lambda _config: (_ for _ in ()).throw(RuntimeError("discovery failed")),
    )
    bridge = LocalLLMBridge(config=SimpleNamespace())
    assert bridge.available is False


def test_local_llm_complete_without_provider_and_fallback_disambiguation(monkeypatch):
    monkeypatch.setattr(LocalLLMBridge, "_init", lambda self: None)
    bridge = LocalLLMBridge()
    with pytest.raises(RuntimeError, match="No LLM provider"):
        asyncio.run(bridge._complete("prompt"))

    candidates = [
        IntentResult(intent=IntentType.CODING, confidence=0.4),
        IntentResult(intent=IntentType.WRITING, confidence=0.3),
    ]
    frame = PerceptionFrame(app_name="Code", screen_type="editor")
    assert asyncio.run(bridge.disambiguate_intent(frame, candidates)) is candidates[0]
    empty = asyncio.run(bridge.disambiguate_intent(frame, []))
    assert empty.intent == IntentType.UNKNOWN


def test_local_llm_disambiguation_no_match_and_exception(monkeypatch):
    monkeypatch.setattr(LocalLLMBridge, "_init", lambda self: None)
    bridge = LocalLLMBridge()
    frame = PerceptionFrame(app_name="Code", screen_type="editor", window_title="main.py")
    candidates = [
        IntentResult(intent=IntentType.CODING, confidence=0.4),
        IntentResult(intent=IntentType.WRITING, confidence=0.3),
    ]

    bridge._provider = _Provider(content="something unrelated")
    assert asyncio.run(bridge.disambiguate_intent(frame, candidates)) is candidates[0]

    async def broken(*_args, **_kwargs):
        raise RuntimeError("completion failed")

    monkeypatch.setattr(bridge, "_complete", broken)
    assert asyncio.run(bridge.disambiguate_intent(frame, candidates)) is candidates[0]


def test_local_llm_generate_and_suggest_fail_closed(monkeypatch):
    monkeypatch.setattr(LocalLLMBridge, "_init", lambda self: None)
    bridge = LocalLLMBridge()
    with pytest.raises(RuntimeError, match="No LLM provider"):
        asyncio.run(bridge.generate_recipe("demo"))

    frame = PerceptionFrame(app_name="Code")
    intent = IntentResult(intent=IntentType.CODING, confidence=0.8)
    assert asyncio.run(bridge.suggest_action(frame, intent)) is None

    bridge._provider = _Provider(content="not-json")
    assert asyncio.run(bridge.suggest_action(frame, intent)) is None

    bridge._provider = _Provider(content='{"type":"not-real","params":{}}')
    assert asyncio.run(bridge.suggest_action(frame, intent)) is None


def test_local_llm_parse_json_fence_variants():
    assert LocalLLMBridge._parse_json('  {"x":1}  ') == {"x": 1}
    assert LocalLLMBridge._parse_json('```\n{"x":2}\n```') == {"x": 2}
    assert LocalLLMBridge._parse_json('```json\n{"x":3}\n```') == {"x": 3}


def test_router_config_key_defaults_and_explicit_providers(monkeypatch):
    router.reset_cache()
    assert router._config_key(None) == ("default",)

    ollama = _Provider(name="ollama")
    compat = _Provider(name="compat")
    monkeypatch.setattr(router, "_make_ollama", lambda _config: ollama)
    monkeypatch.setattr(router, "_make_openai_compat", lambda _config: compat)

    assert router._discover(PhantomConfig(llm_provider="ollama")) is ollama
    assert router._discover(PhantomConfig(llm_provider="openai_compat")) is compat


def test_router_auto_uses_compat_then_null(monkeypatch):
    ollama = _Provider(available=False, name="ollama")
    compat = _Provider(available=True, name="compat")
    monkeypatch.setattr(router, "_make_ollama", lambda _config: ollama)
    monkeypatch.setattr(router, "_make_openai_compat", lambda _config: compat)
    config = PhantomConfig(llm_provider="auto", llm_base_url="http://localhost:1234")
    assert router._discover(config) is compat

    compat._available = False
    assert isinstance(router._discover(config), NullProvider)

    config = PhantomConfig(llm_provider="auto", llm_base_url="")
    assert isinstance(router._discover(config), NullProvider)


def test_router_discover_none_and_constructor_arguments(monkeypatch):
    fake_config = PhantomConfig(llm_provider="none")
    monkeypatch.setattr(
        "phantom.config.PhantomConfig",
        lambda: fake_config,
    )
    assert isinstance(router._discover(None), NullProvider)

    captured = {}

    class _Ollama:
        def __init__(self, **kwargs):
            captured["ollama"] = kwargs

    class _Compat:
        def __init__(self, **kwargs):
            captured["compat"] = kwargs

    monkeypatch.setattr("phantom.llm.ollama.OllamaProvider", _Ollama)
    monkeypatch.setattr("phantom.llm.openai_compat.OpenAICompatProvider", _Compat)
    config = PhantomConfig(
        ollama_host="http://ollama",
        llm_model="model",
        llm_timeout=12.0,
        llm_base_url="http://compat",
        llm_api_key="test-key",
    )
    assert router._make_ollama(config).__class__ is _Ollama
    assert router._make_openai_compat(config).__class__ is _Compat
    assert captured["ollama"]["host"] == "http://ollama"
    assert captured["ollama"]["timeout_read"] == 12.0
    assert captured["compat"]["base_url"] == "http://compat"
    assert captured["compat"]["api_key"] == "test-key"


def test_safety_sequence_invalid_shapes_and_custom_blocklists(tmp_path):
    policy = SafetyPolicy(
        blocked_apps=["SecretApp"],
        blocked_paths=[str(tmp_path / "private")],
        blocked_commands=["dangerous"],
        blocked_domains=["blocked.example"],
        approval_store_path=tmp_path / "approvals.json",
    )
    policy.trust_level = TrustLevel.AUTO_EXECUTE

    assert (
        policy.allow(ActionRequest(type=PhantomActionType.SEQUENCE, params={"steps": "bad"}))
        is False
    )
    assert (
        policy.allow(ActionRequest(type=PhantomActionType.SEQUENCE, params={"steps": ["bad"]}))
        is False
    )
    assert (
        policy.allow(
            ActionRequest(
                type=PhantomActionType.SEQUENCE,
                params={"steps": [{"type": "not-real"}]},
            )
        )
        is False
    )
    assert (
        policy.allow(
            ActionRequest(type=PhantomActionType.APP_ACTIVATE, params={"app": "SecretApp"})
        )
        is False
    )
    assert (
        policy.allow(
            ActionRequest(
                type=PhantomActionType.FILE_OPEN, params={"path": str(tmp_path / "private")}
            )
        )
        is False
    )
    assert (
        policy.allow(
            ActionRequest(type=PhantomActionType.RUN_COMMAND, params={"command": "echo dangerous"})
        )
        is False
    )
    assert (
        policy.allow(
            ActionRequest(
                type=PhantomActionType.URL_OPEN,
                params={"url": "https://blocked.example/path"},
            )
        )
        is False
    )


def test_safety_shell_control_and_path_traversal_fail_closed(tmp_path):
    policy = SafetyPolicy(approval_store_path=tmp_path / "approvals.json")
    policy.trust_level = TrustLevel.AUTO_EXECUTE
    for command in [
        "echo ok; date",
        "echo ok | date",
        "echo $(date)",
        "echo `date`",
        "echo ${HOME}",
        "echo ok\ndate",
    ]:
        request = ActionRequest(type=PhantomActionType.RUN_COMMAND, params={"command": command})
        assert policy.allow(request) is False

    assert policy._has_shell_control(["echo", "literal|value"]) is False
    assert policy._is_blocked_path("../../etc/passwd") is True
    assert policy._is_blocked_path("") is False


def test_safety_open_and_ls_argument_edges(tmp_path):
    policy = SafetyPolicy(approval_store_path=tmp_path / "approvals.json")
    assert policy._open_targets_allowed([]) is False
    assert policy._open_targets_allowed(["-a"]) is False
    assert policy._open_targets_allowed(["--unknown", "x"]) is False
    assert policy._open_targets_allowed(["ftp://example.com"]) is False
    assert policy._open_targets_allowed(["https://example.com"]) is True
    assert policy._ls_targets_allowed(["-"]) is False
    assert policy._ls_targets_allowed(["--bad"]) is False
    assert policy._ls_targets_allowed(["--", "."]) is True


def test_safety_rate_limit_and_approval_callback(tmp_path):
    policy = SafetyPolicy(
        approval_callback=lambda _request: False,
        max_actions_per_minute=1,
        approval_store_path=tmp_path / "approvals.json",
    )
    request = ActionRequest(type=PhantomActionType.TYPE_TEXT, params={"text": "x"})
    policy.trust_level = TrustLevel.APPROVE_EACH
    assert asyncio.run(policy.request_approval(request)) is False

    policy.trust_level = TrustLevel.AUTO_EXECUTE
    assert policy.allow(request) is True
    assert policy.allow(request) is False
