"""Test platform adapter factory selection."""

from phantom.actions.platform import (
    LinuxAdapter,
    MacOSAdapter,
    UnsupportedPlatformAdapter,
    create_platform_adapter,
)


def test_factory_returns_macos_adapter():
    adapter = create_platform_adapter("darwin")
    assert isinstance(adapter, MacOSAdapter)


def test_factory_returns_linux_adapter():
    adapter = create_platform_adapter("linux")
    assert isinstance(adapter, LinuxAdapter)


def test_factory_returns_unsupported_adapter():
    adapter = create_platform_adapter("windows")
    assert isinstance(adapter, UnsupportedPlatformAdapter)
