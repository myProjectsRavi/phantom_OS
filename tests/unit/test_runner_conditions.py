"""Test recipe runner condition evaluation."""

import pytest

from phantom.automation.runner import RecipeRunner


class _DummyClipboard:
    def get(self):
        return ""


class _DummyExecutor:
    clipboard = _DummyClipboard()


@pytest.fixture
def runner():
    return RecipeRunner(_DummyExecutor())


def test_condition_true_with_boolean_and_comparison(runner):
    values = {"app": "Code", "blocked": False}
    assert runner._condition_true("app == 'Code' and not blocked", values)


def test_condition_false_with_membership(runner):
    values = {"app": "Safari", "allowed": ["Code", "Terminal"]}
    assert not runner._condition_true("app in allowed", values)


def test_condition_rejects_unsupported_expression(runner):
    with pytest.raises(ValueError):
        runner._condition_true("__import__('os').system('whoami')", {})
