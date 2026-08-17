"""Test safety policy."""

import asyncio
import json
import stat

from phantom.models import ActionRequest, PhantomActionType, TrustLevel
from phantom.safety.policy import SafetyPolicy


def test_blocked_app():
    policy = SafetyPolicy()
    request = ActionRequest(type=PhantomActionType.APP_ACTIVATE, params={"app": "1Password"})
    assert not policy.allow(request)


def test_blocked_command():
    policy = SafetyPolicy()
    request = ActionRequest(type=PhantomActionType.RUN_COMMAND, params={"command": "sudo rm -rf /"})
    assert not policy.allow(request)


def test_blocked_domain_url():
    policy = SafetyPolicy(blocked_domains=["bank", "internal.example"])
    request = ActionRequest(
        type=PhantomActionType.URL_OPEN,
        params={"url": "https://mybank.example/login"},
    )
    assert not policy.allow(request)


def test_normal_action_allowed():
    policy = SafetyPolicy()
    request = ActionRequest(type=PhantomActionType.APP_ACTIVATE, params={"app": "Safari"})
    assert policy.allow(request)


def test_suggest_only_blocks():
    policy = SafetyPolicy()
    policy.trust_level = TrustLevel.SUGGEST_ONLY
    request = ActionRequest(type=PhantomActionType.TYPE_TEXT, params={"text": "hi"})
    assert not policy.allow(request)


def test_emergency_stop():
    policy = SafetyPolicy()
    policy.emergency_stop()
    request = ActionRequest(type=PhantomActionType.TYPE_TEXT, params={"text": "hi"})
    assert not policy.allow(request)
    policy.resume()
    assert policy.allow(request)


def test_consecutive_errors_circuit_breaker():
    policy = SafetyPolicy()
    policy.record_error()
    policy.record_error()
    policy.record_error()
    request = ActionRequest(type=PhantomActionType.TYPE_TEXT, params={"text": "hi"})
    assert not policy.allow(request)


def test_approval_is_denied_by_default():
    policy = SafetyPolicy()
    request = ActionRequest(
        type=PhantomActionType.TYPE_TEXT, params={"text": "hi"}, source="recipe"
    )
    assert asyncio.run(policy.request_approval(request)) is False


def test_approval_env_override(monkeypatch):
    monkeypatch.setenv("PHANTOM_AUTO_APPROVE", "true")
    policy = SafetyPolicy()
    request = ActionRequest(
        type=PhantomActionType.TYPE_TEXT, params={"text": "hi"}, source="recipe"
    )
    assert asyncio.run(policy.request_approval(request)) is True


def test_trust_level_drives_approval_requirement():
    request = ActionRequest(type=PhantomActionType.TYPE_TEXT, params={"text": "hi"})
    policy = SafetyPolicy()

    policy.trust_level = TrustLevel.APPROVE_EACH
    assert policy.requires_approval(request) is True

    policy.trust_level = TrustLevel.APPROVE_NEW
    assert policy.requires_approval(request) is True

    policy.trust_level = TrustLevel.AUTO_EXECUTE
    assert policy.requires_approval(request) is False


def test_explicit_approval_is_required_in_auto_execute():
    policy = SafetyPolicy()
    policy.trust_level = TrustLevel.AUTO_EXECUTE
    request = ActionRequest(
        type=PhantomActionType.TYPE_TEXT,
        params={"text": "hi"},
        requires_approval=True,
    )
    assert policy.requires_approval(request) is True
    assert asyncio.run(policy.request_approval(request)) is False


def test_blocked_requests_do_not_consume_rate_budget():
    policy = SafetyPolicy(max_actions_per_minute=1)
    blocked = ActionRequest(type=PhantomActionType.APP_ACTIVATE, params={"app": "1Password"})
    allowed = ActionRequest(type=PhantomActionType.APP_ACTIVATE, params={"app": "Safari"})

    assert policy.allow(blocked) is False
    assert policy.allow(allowed) is True


def test_approve_new_learning_persists_across_policy_instances(tmp_path):
    store = tmp_path / "approvals.json"
    request = ActionRequest(
        type=PhantomActionType.TYPE_TEXT,
        params={"text": "sensitive text that must not be persisted"},
        source="recipe:demo",
    )

    for _ in range(5):
        policy = SafetyPolicy(
            approval_callback=lambda _request: True,
            approval_store_path=store,
        )
        policy.trust_level = TrustLevel.APPROVE_NEW
        assert policy.requires_approval(request) is True
        assert asyncio.run(policy.request_approval(request)) is True

    reloaded = SafetyPolicy(approval_store_path=store)
    reloaded.trust_level = TrustLevel.APPROVE_NEW
    assert reloaded.requires_approval(request) is False

    payload = json.loads(store.read_text())
    assert payload["counts"] == {}
    assert len(payload["approved"]) == 1
    assert len(payload["approved"][0]) == 64
    assert "sensitive text" not in store.read_text()
    assert stat.S_IMODE(store.stat().st_mode) == 0o600


def test_corrupt_approval_store_fails_closed(tmp_path):
    store = tmp_path / "approvals.json"
    store.write_text("not-json")
    policy = SafetyPolicy(approval_store_path=store)
    policy.trust_level = TrustLevel.APPROVE_NEW
    request = ActionRequest(type=PhantomActionType.TYPE_TEXT, params={"text": "hi"})
    assert policy.requires_approval(request) is True
