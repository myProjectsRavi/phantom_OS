"""Regression tests for daemon control-plane hardening."""

from __future__ import annotations

import asyncio
import stat
import threading
import time
from pathlib import Path

import pytest

from phantom.actions.executor import ActionExecutor
from phantom.daemon import PhantomDaemon
from phantom.models import ActionRequest, ActionResult, PhantomActionType, TrustLevel
from phantom.safety.policy import SafetyPolicy


def test_blocking_native_dispatch_does_not_starve_emergency_stop(monkeypatch):
    policy = SafetyPolicy()
    policy.trust_level = TrustLevel.AUTO_EXECUTE
    executor = ActionExecutor(safety=policy)
    release = threading.Event()

    def blocking_dispatch(request):
        release.wait(timeout=0.5)
        return ActionResult(success=True, action_type=request.type)

    monkeypatch.setattr(executor, "_dispatch", blocking_dispatch)

    async def run():
        async def stop_soon():
            await asyncio.sleep(0.01)
            policy.emergency_stop()
            release.set()

        started = time.perf_counter()
        result, _ = await asyncio.gather(
            executor.execute(ActionRequest(type=PhantomActionType.WAIT)),
            stop_soon(),
        )
        elapsed = time.perf_counter() - started
        return result, elapsed

    result, elapsed = asyncio.run(run())
    assert result.success is True
    assert elapsed < 0.25
    assert policy.is_stopped is True

    blocked = asyncio.run(executor.execute(ActionRequest(type=PhantomActionType.WAIT)))
    assert blocked.success is False
    assert blocked.error == "Blocked by safety"


def test_daemon_instance_lock_rejects_second_process_owner(tmp_path):
    first = object.__new__(PhantomDaemon)
    first._lock_file = Path(tmp_path) / "phantom.lock"
    first._lock_handle = None

    second = object.__new__(PhantomDaemon)
    second._lock_file = first._lock_file
    second._lock_handle = None

    first._acquire_instance_lock()
    try:
        assert stat.S_IMODE(first._lock_file.stat().st_mode) == 0o600
        with pytest.raises(RuntimeError, match="already running"):
            second._acquire_instance_lock()
    finally:
        first._release_instance_lock()


def test_pid_file_is_owner_only(tmp_path):
    daemon = object.__new__(PhantomDaemon)
    daemon._pid_file = Path(tmp_path) / "phantom.pid"

    daemon._write_pid()

    assert daemon._pid_file.read_text().isdigit()
    assert stat.S_IMODE(daemon._pid_file.stat().st_mode) == 0o600
    daemon._cleanup_pid()
    assert not daemon._pid_file.exists()
