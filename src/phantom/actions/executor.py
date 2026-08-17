"""Action executor with safety integration."""

from __future__ import annotations

import asyncio
import platform
import shlex
import subprocess
import time
from typing import Optional

from phantom.actions.app_control import AppController
from phantom.actions.clipboard import ClipboardManager
from phantom.actions.keyboard import KeyboardSimulator
from phantom.applescript import notification_script, run_osascript
from phantom.events import EventBus, PhantomEvents
from phantom.models import ActionRequest, ActionResult, PhantomActionType
from phantom.safety.policy import SafetyPolicy


class ActionExecutor:
    """Execute validated desktop actions through concrete action adapters."""

    ALLOWED_COMMANDS = SafetyPolicy.ALLOWED_COMMANDS

    def __init__(self, safety: SafetyPolicy | None = None, event_bus: EventBus | None = None):
        self._keyboard = KeyboardSimulator()
        self._clipboard = ClipboardManager()
        self._app = AppController()
        self._safety = safety or SafetyPolicy()
        self._events = event_bus or EventBus()
        self._history: list[ActionResult] = []

    async def execute(self, request: ActionRequest) -> ActionResult:
        """Execute a request through the single authoritative safety boundary.

        Blocking native adapters run in a worker thread so the daemon event loop can
        continue servicing emergency-stop and other local control requests while an
        already-authorized OS operation is in flight.
        """
        if not self._safety.allow(request):
            self._events.emit(PhantomEvents.ACTION_BLOCKED, {"type": request.type.value})
            return ActionResult(success=False, action_type=request.type, error="Blocked by safety")

        if self._safety.requires_approval(request):
            approved = await self._safety.request_approval(request)
            if not approved:
                return ActionResult(
                    success=False, action_type=request.type, error="Rejected by user"
                )

        self._events.emit(PhantomEvents.ACTION_REQUESTED, {"type": request.type.value})
        start = time.time()
        if request.type == PhantomActionType.SEQUENCE:
            result = await self._exec_sequence(request)
        else:
            result = await asyncio.to_thread(self._dispatch, request)
        result.duration_ms = (time.time() - start) * 1000

        if result.success:
            self._safety.record_success()
            self._events.emit(
                PhantomEvents.ACTION_EXECUTED,
                {"type": request.type.value, "ms": result.duration_ms},
            )
        else:
            self._safety.record_error()
            self._events.emit(
                PhantomEvents.ACTION_FAILED, {"type": request.type.value, "error": result.error}
            )

        self._history.append(result)
        if len(self._history) > 1000:
            self._history = self._history[-1000:]
        return result

    def _dispatch(self, req: ActionRequest) -> ActionResult:
        """Route one already-authorized non-sequence request to its adapter."""
        action_type = req.type
        params = req.params
        try:
            if action_type == PhantomActionType.TYPE_TEXT:
                return self._keyboard.type_text(params.get("text", ""))
            if action_type == PhantomActionType.PRESS_KEY:
                modifiers = params.get("modifiers")
                safe_modifiers = modifiers if isinstance(modifiers, list) else None
                return self._keyboard.press_key(params.get("key", ""), safe_modifiers)
            if action_type == PhantomActionType.CLIPBOARD_COPY:
                content = self._clipboard.copy()
                return ActionResult(
                    success=True,
                    action_type=action_type,
                    metadata={"content": content},
                )
            if action_type == PhantomActionType.CLIPBOARD_PASTE:
                self._clipboard.paste(params.get("content"))
                return ActionResult(success=True, action_type=action_type)
            if action_type == PhantomActionType.CLIPBOARD_SET:
                self._clipboard.set(params.get("content", ""))
                return ActionResult(success=True, action_type=action_type)
            if action_type == PhantomActionType.APP_ACTIVATE:
                return self._app.activate(params.get("app", ""))
            if action_type == PhantomActionType.URL_OPEN:
                return self._app.open_url(params.get("url", ""))
            if action_type == PhantomActionType.FILE_OPEN:
                return self._app.open_file(params.get("path", ""))
            if action_type == PhantomActionType.RUN_COMMAND:
                args = self._parse_command(params.get("command", ""))
                if not args:
                    return ActionResult(
                        success=False,
                        action_type=action_type,
                        error="Invalid command",
                    )
                executable = args[0]
                if executable not in self.ALLOWED_COMMANDS:
                    return ActionResult(
                        success=False,
                        action_type=action_type,
                        error=f"Command not allowed: {executable}",
                    )
                output = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                return ActionResult(
                    success=output.returncode == 0,
                    action_type=action_type,
                    error=(
                        None
                        if output.returncode == 0
                        else f"Command exited with {output.returncode}"
                    ),
                    metadata={
                        "stdout": output.stdout[:2000],
                        "returncode": output.returncode,
                    },
                )
            if action_type == PhantomActionType.WAIT:
                time.sleep(params.get("seconds", 1))
                return ActionResult(success=True, action_type=action_type)
            if action_type == PhantomActionType.NOTIFICATION:
                title = params.get("title", "PHANTOM")
                message = params.get("message", "")
                system = platform.system().lower()
                if system == "darwin":
                    completed = run_osascript(notification_script(title, message), timeout=3)
                    if completed.returncode != 0:
                        return ActionResult(
                            success=False,
                            action_type=action_type,
                            error=f"Notification failed with {completed.returncode}",
                        )
                elif system == "linux":
                    completed = subprocess.run(
                        ["notify-send", title, message], timeout=3, check=False
                    )
                    if completed.returncode != 0:
                        return ActionResult(
                            success=False,
                            action_type=action_type,
                            error=f"Notification failed with {completed.returncode}",
                        )
                return ActionResult(success=True, action_type=action_type)
            if action_type == PhantomActionType.SEQUENCE:
                return ActionResult(
                    success=False,
                    action_type=action_type,
                    error="Sequences must execute through the async safety path",
                )
            return ActionResult(
                success=False,
                action_type=action_type,
                error="Unknown action",
            )
        except Exception as exc:
            return ActionResult(success=False, action_type=action_type, error=str(exc))

    async def _exec_sequence(self, request: ActionRequest) -> ActionResult:
        """Execute every nested step through the same safety/approval boundary."""
        steps = request.params.get("steps", [])
        if not isinstance(steps, list):
            return ActionResult(
                success=False,
                action_type=PhantomActionType.SEQUENCE,
                error="Invalid sequence steps",
            )
        for step in steps:
            if not isinstance(step, dict) or "type" not in step:
                return ActionResult(
                    success=False,
                    action_type=PhantomActionType.SEQUENCE,
                    error="Invalid sequence step",
                )
            try:
                sub = ActionRequest(
                    type=PhantomActionType(step["type"]),
                    params=step.get("params", {}),
                    requires_approval=bool(step.get("requires_approval", False)),
                    source=request.source or "sequence",
                )
            except (TypeError, ValueError) as exc:
                return ActionResult(
                    success=False,
                    action_type=PhantomActionType.SEQUENCE,
                    error=f"Invalid sequence step: {exc}",
                )
            result = await self.execute(sub)
            if not result.success:
                return result
            delay_after = step.get("delay_after", 0)
            if delay_after:
                await asyncio.sleep(delay_after)
        return ActionResult(success=True, action_type=PhantomActionType.SEQUENCE)

    def _parse_command(self, raw: object) -> list[str]:
        """Parse and sanitize command input into an argv list."""
        if isinstance(raw, list):
            return [str(part) for part in raw if str(part)]
        if not isinstance(raw, str):
            return []
        if not raw.strip():
            return []
        if any(token in raw for token in (";", "|", "&&", "||", ">", "<", "$(", "`")):
            return []
        try:
            return shlex.split(raw)
        except ValueError:
            return []

    async def undo_last_async(self) -> Optional[ActionResult]:
        """Undo the latest reversible action through the normal safety boundary."""
        if self._history and self._history[-1].undo_info:
            info = self._history[-1].undo_info
            try:
                request = ActionRequest(
                    type=PhantomActionType(info["type"]),
                    params=info.get("params", {}),
                    requires_approval=bool(info.get("requires_approval", False)),
                    source="undo",
                )
            except (KeyError, TypeError, ValueError):
                return ActionResult(
                    success=False,
                    action_type=PhantomActionType.NOTIFICATION,
                    error="Invalid undo metadata",
                )
            return await self.execute(request)
        return None

    def undo_last(self) -> Optional[ActionResult]:
        """Synchronous compatibility wrapper for non-daemon callers."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.undo_last_async())
        raise RuntimeError("Use await undo_last_async() from an active event loop")

    @property
    def clipboard(self):
        """Expose clipboard adapter for read/write/history operations."""
        return self._clipboard
