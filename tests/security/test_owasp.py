"""Security regression tests for the live PhantomOS desktop runtime."""

from __future__ import annotations

import asyncio

import pytest

from phantom.actions.app_control import AppController
from phantom.actions.executor import ActionExecutor
from phantom.applescript import escape_applescript
from phantom.models import ActionRequest, ActionResult, PhantomActionType, TrustLevel
from phantom.safety.policy import SafetyPolicy


def test_path_traversal_into_etc_is_blocked():
    assert SafetyPolicy().allow(ActionRequest(type=PhantomActionType.FILE_OPEN, params={"path": "../../etc/passwd"})) is False


def test_sensitive_home_path_is_blocked():
    assert SafetyPolicy().allow(ActionRequest(type=PhantomActionType.FILE_OPEN, params={"path": "~/.ssh/config"})) is False


@pytest.mark.parametrize("url", ["https://bank.example/login", "https://internal.example/admin"])
def test_configured_sensitive_domains_are_blocked(url):
    policy = SafetyPolicy(blocked_domains=["bank", "internal.example"])
    assert policy.allow(ActionRequest(type=PhantomActionType.URL_OPEN, params={"url": url})) is False


def test_non_http_url_is_rejected_before_native_open(monkeypatch):
    controller = AppController(); calls = []
    monkeypatch.setattr("phantom.actions.app_control.subprocess.run", lambda *args, **kwargs: calls.append((args, kwargs)))
    result = controller.open_url("file:///etc/passwd")
    assert result.success is False; assert calls == []


def test_applescript_escaping_quotes_and_backslashes():
    payload = '" & do shell script "id" & "\\tail'
    escaped = escape_applescript(payload)
    assert '\\"' in escaped; assert "\\\\" in escaped; assert escaped != payload


def test_suggest_only_cannot_execute(monkeypatch):
    policy = SafetyPolicy(); policy.trust_level = TrustLevel.SUGGEST_ONLY
    executor = ActionExecutor(safety=policy); dispatched = []
    monkeypatch.setattr(executor, "_dispatch", lambda request: dispatched.append(request))
    result = asyncio.run(executor.execute(ActionRequest(type=PhantomActionType.TYPE_TEXT, params={"text": "hello"})))
    assert result.success is False; assert dispatched == []


def test_three_native_failures_trip_circuit_breaker(monkeypatch):
    policy = SafetyPolicy(); policy.trust_level = TrustLevel.AUTO_EXECUTE
    executor = ActionExecutor(safety=policy)
    monkeypatch.setattr(executor, "_dispatch", lambda request: ActionResult(success=False, action_type=request.type, error="native failure"))
    request = ActionRequest(type=PhantomActionType.NOTIFICATION)
    for _ in range(3):
        result = asyncio.run(executor.execute(request)); assert result.success is False
    assert policy.is_stopped is True
    blocked = asyncio.run(executor.execute(request)); assert blocked.error == "Blocked by safety"


def test_explicit_approval_flag_is_honored_even_in_auto_execute(monkeypatch):
    policy = SafetyPolicy(); policy.trust_level = TrustLevel.AUTO_EXECUTE
    executor = ActionExecutor(safety=policy); dispatched = []
    monkeypatch.setattr(executor, "_dispatch", lambda request: dispatched.append(request))
    result = asyncio.run(executor.execute(ActionRequest(type=PhantomActionType.TYPE_TEXT, params={"text": "requires consent"}, requires_approval=True)))
    assert result.success is False; assert result.error == "Rejected by user"; assert dispatched == []
