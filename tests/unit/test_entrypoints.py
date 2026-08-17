"""Entry-point and error hierarchy coverage tests."""

from __future__ import annotations

import runpy
import sys
from types import SimpleNamespace

from phantom.errors import (
    ActionError,
    EmergencyStopError,
    IntentError,
    PerceptionError,
    PhantomError,
    PlatformError,
    RecipeError,
    SafetyError,
)


def test_error_hierarchy():
    assert issubclass(PerceptionError, PhantomError)
    assert issubclass(ActionError, PhantomError)
    assert issubclass(RecipeError, PhantomError)
    assert issubclass(SafetyError, PhantomError)
    assert issubclass(IntentError, PhantomError)
    assert issubclass(PlatformError, PhantomError)
    assert issubclass(EmergencyStopError, PhantomError)


def test_module_entrypoint_calls_cli_main(monkeypatch):
    called = []
    monkeypatch.setitem(
        sys.modules, "phantom.cli", SimpleNamespace(main=lambda: called.append(True))
    )
    runpy.run_module("phantom.__main__", run_name="__main__")
    assert called == [True]
