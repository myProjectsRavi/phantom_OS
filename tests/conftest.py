"""Test fixtures."""

import pytest

from phantom.models import ActionType, UserAction


@pytest.fixture(autouse=True)
def isolate_approval_store(tmp_path, monkeypatch):
    """Prevent tests from reading or mutating a developer's real trust store."""
    monkeypatch.setenv("PHANTOM_APPROVAL_STORE", str(tmp_path / "approvals.json"))


@pytest.fixture
def sample_actions():
    return [
        UserAction(type=ActionType.APP_SWITCH, app_name="Chrome"),
        UserAction(type=ActionType.CLIPBOARD_COPY, app_name="Chrome"),
        UserAction(type=ActionType.APP_SWITCH, app_name="Slack"),
        UserAction(type=ActionType.CLIPBOARD_PASTE, app_name="Slack"),
        UserAction(type=ActionType.APP_SWITCH, app_name="Chrome"),
        UserAction(type=ActionType.CLIPBOARD_COPY, app_name="Chrome"),
        UserAction(type=ActionType.APP_SWITCH, app_name="Slack"),
        UserAction(type=ActionType.CLIPBOARD_PASTE, app_name="Slack"),
        UserAction(type=ActionType.APP_SWITCH, app_name="Chrome"),
        UserAction(type=ActionType.CLIPBOARD_COPY, app_name="Chrome"),
        UserAction(type=ActionType.APP_SWITCH, app_name="Slack"),
        UserAction(type=ActionType.CLIPBOARD_PASTE, app_name="Slack"),
    ]
