"""Resource-level authorization tests for generic command execution."""

from __future__ import annotations

import pytest

from phantom.models import ActionRequest, PhantomActionType, TrustLevel
from phantom.safety.policy import SafetyPolicy


def _allowed(command) -> bool:
    policy = SafetyPolicy()
    policy.trust_level = TrustLevel.AUTO_EXECUTE
    return policy.allow(
        ActionRequest(type=PhantomActionType.RUN_COMMAND, params={"command": command})
    )


@pytest.mark.parametrize(
    "command",
    [
        ["ls", "~/.ssh"],
        ["ls", "/etc"],
        ["ls", "-R", "/"],
        ["open", "file:///etc/passwd"],
        ["open", "ftp://example.com/file"],
        ["screencapture", "/tmp/capture.png"],
        ["tesseract", "/tmp/input.png", "/tmp/output"],
        ["/bin/ls", "/tmp"],
    ],
)
def test_resource_aliases_and_unneeded_commands_fail_closed(command):
    assert _allowed(command) is False


@pytest.mark.parametrize(
    "command",
    [
        ["ls"],
        ["ls", "-la", "/tmp"],
        ["echo", "hello"],
        ["date"],
        ["pwd"],
        ["open", "https://example.com"],
        ["open", "-a", "Safari"],
        ["killall", "Slack"],
    ],
)
def test_explicit_command_subset_stays_available(command):
    assert _allowed(command) is True
