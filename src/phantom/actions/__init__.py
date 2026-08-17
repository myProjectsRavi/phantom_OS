"""Action execution package."""

from phantom.actions.app_control import AppController
from phantom.actions.clipboard import ClipboardManager
from phantom.actions.executor import ActionExecutor
from phantom.actions.keyboard import KeyboardSimulator
from phantom.actions.platform import PlatformAdapter, create_platform_adapter

__all__ = [
    "ActionExecutor",
    "KeyboardSimulator",
    "ClipboardManager",
    "AppController",
    "PlatformAdapter",
    "create_platform_adapter",
]
