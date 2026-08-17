"""Test action executor security and command handling."""

from phantom.actions.executor import ActionExecutor
from phantom.models import ActionRequest, PhantomActionType


def test_run_command_rejects_shell_operators():
    executor = ActionExecutor()
    result = executor._dispatch(
        ActionRequest(
            type=PhantomActionType.RUN_COMMAND,
            params={"command": "echo ok; rm -rf /"},
        )
    )
    assert not result.success
    assert result.error == "Invalid command"


def test_run_command_rejects_non_allowlisted_binary():
    executor = ActionExecutor()
    result = executor._dispatch(
        ActionRequest(
            type=PhantomActionType.RUN_COMMAND,
            params={"command": "uname -a"},
        )
    )
    assert not result.success
    assert result.error == "Command not allowed: uname"


def test_run_command_executes_allowlisted_command():
    executor = ActionExecutor()
    result = executor._dispatch(
        ActionRequest(
            type=PhantomActionType.RUN_COMMAND,
            params={"command": ["echo", "phantom"]},
        )
    )
    assert result.success
    assert "phantom" in result.metadata.get("stdout", "")
