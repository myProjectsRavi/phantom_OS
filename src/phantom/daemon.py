"""PHANTOM background daemon."""

from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import signal
import time
from pathlib import Path
from typing import IO

from phantom.agent import PhantomAgent
from phantom.control import socket_path
from phantom.models import TriggerEvent, TrustLevel

logger = logging.getLogger("phantom.daemon")


class PhantomDaemon:
    """Background daemon that runs the perception-intent-action loop."""

    def __init__(self, config_path=None):
        self._agent = PhantomAgent.init(config_path)
        self._config_path = Path(config_path or Path.home() / ".phantom" / "config.toml")
        self._running = False
        self._previous_app = ""
        self._app_switch_time = time.time()
        self._last_schedule_check: str | None = None
        self._last_discovery: float = 0.0
        self._pid_file = Path.home() / ".phantom" / "phantom.pid"
        self._lock_file = Path.home() / ".phantom" / "phantom.lock"
        self._lock_handle: IO[str] | None = None
        self._socket_path = socket_path()
        self._control_server: asyncio.AbstractServer | None = None

    def run(self):
        """Run the daemon (blocking), allowing only one instance per user."""
        self._acquire_instance_lock()
        try:
            self._running = True
            self._agent.start()
            self._write_pid()
            signal.signal(signal.SIGINT, self._handle_signal)
            signal.signal(signal.SIGTERM, self._handle_signal)
            logger.info("PHANTOM daemon running")
            try:
                asyncio.run(self._run_async())
            except KeyboardInterrupt:
                pass
        finally:
            self._agent.stop()
            self._cleanup_control_socket()
            self._cleanup_pid()
            self._release_instance_lock()
            logger.info("PHANTOM daemon stopped")

    async def _run_async(self):
        """Run control server and main loop in one event loop."""
        await self._start_control_server()
        await self._loop()

    async def _start_control_server(self) -> None:
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        self._cleanup_control_socket()
        self._control_server = await asyncio.start_unix_server(
            self._handle_control_client,
            path=str(self._socket_path),
        )
        os.chmod(self._socket_path, 0o600)

    async def _handle_control_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            raw = await asyncio.wait_for(reader.readline(), timeout=3.0)
            request = json.loads(raw.decode("utf-8")) if raw else {}
            response = await self._handle_control_command(request)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Control request failed: %s", exc)
            response = {"ok": False, "error": str(exc)}
        writer.write((json.dumps(response, default=str) + "\n").encode("utf-8"))
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def _handle_control_command(self, request: dict) -> dict:
        command = request.get("command", "")
        if command == "status":
            return {"ok": True, "pid": os.getpid(), "status": self._agent.status}
        if command == "stats":
            return {"ok": True, "pid": os.getpid(), "stats": self._agent.stats()}
        if command == "trust":
            level = TrustLevel(str(request.get("level", "")))
            self._agent.set_trust_level(level)
            self._persist_trust_level(level)
            return {"ok": True, "pid": os.getpid(), "trust_level": level.value}
        if command == "emergency_stop":
            self._agent.emergency_stop()
            return {"ok": True, "pid": os.getpid(), "emergency_stopped": True}
        if command == "resume":
            self._agent._safety.resume()
            return {"ok": True, "pid": os.getpid(), "emergency_stopped": False}
        if command == "undo":
            result = await self._agent._executor.undo_last_async()
            if result is None:
                return {"ok": True, "pid": os.getpid(), "undone": False}
            return {
                "ok": result.success,
                "pid": os.getpid(),
                "undone": result.success,
                "action_type": result.action_type.value,
                "error": result.error,
            }
        if command == "clipboard_history":
            return {
                "ok": True,
                "pid": os.getpid(),
                "history": self._agent.clipboard_history(int(request.get("limit", 20))),
            }
        if command == "perceive":
            frame = self._agent.perceive()
            return {
                "ok": True,
                "pid": os.getpid(),
                "frame": None
                if frame is None
                else {
                    "app_name": frame.app_name,
                    "window_title": frame.window_title,
                    "screen_type": frame.screen_type,
                    "elements": len(frame.elements),
                    "is_typing": frame.is_typing,
                    "idle_seconds": frame.idle_seconds,
                },
            }
        if command == "intent":
            result = self._agent.current_intent()
            return {
                "ok": True,
                "pid": os.getpid(),
                "intent": None
                if result is None
                else {
                    "intent": result.intent.value,
                    "confidence": result.confidence,
                    "source_app": result.source_app,
                },
            }
        if command == "predictions":
            return {
                "ok": True,
                "pid": os.getpid(),
                "predictions": [
                    {
                        "action_type": item.action_type.value,
                        "target_app": item.target_app,
                        "confidence": item.confidence,
                        "expected_in_seconds": item.expected_in_seconds,
                        "source": item.source,
                    }
                    for item in self._agent.predictions()
                ],
            }
        return {"ok": False, "error": f"Unknown control command: {command}"}

    def _persist_trust_level(self, level: TrustLevel) -> None:
        """Persist only the trust setting while preserving the rest of config.toml."""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        text = self._config_path.read_text() if self._config_path.exists() else "[phantom]\n"
        lines = text.splitlines()
        in_phantom = False
        replaced = False
        insert_at: int | None = None
        for index, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                if in_phantom and insert_at is None:
                    insert_at = index
                in_phantom = stripped == "[phantom]"
                continue
            if in_phantom and stripped.startswith("trust_level"):
                lines[index] = f'trust_level = "{level.value}"'
                replaced = True
                break
        if not replaced:
            if "[phantom]" not in [line.strip() for line in lines]:
                lines.extend(["", "[phantom]", f'trust_level = "{level.value}"'])
            else:
                position = insert_at if insert_at is not None else len(lines)
                lines.insert(position, f'trust_level = "{level.value}"')
        self._config_path.write_text("\n".join(lines).rstrip() + "\n")
        os.chmod(self._config_path, 0o600)

    async def _loop(self):
        """Main perception-intent-action loop."""
        while self._running:
            try:
                await self._tick()
            except Exception as exc:  # noqa: BLE001
                logger.error("Tick error: %s", exc)
            await asyncio.sleep(self._agent.frame_interval)

    async def _tick(self):
        """Single iteration of the main loop."""
        frame = self._agent.perceive()
        if not frame:
            return

        if frame.app_name != self._previous_app:
            event = TriggerEvent(
                type="app_switch",
                data={
                    "app_name": frame.app_name,
                    "previous_app": self._previous_app,
                    "running_apps": [],
                },
            )
            for recipe in self._agent.matching_recipes(event):
                logger.info("Trigger fired: %s", recipe.name)
                await self._agent.run_recipe(recipe.name)
            self._previous_app = frame.app_name
            self._app_switch_time = time.time()

        self._agent.current_intent()

        if frame.text_content:
            text = " ".join(frame.text_content.values())
            event = TriggerEvent(
                type="content_match",
                data={"text": text, "app_name": frame.app_name},
            )
            for recipe in self._agent.matching_recipes(event):
                await self._agent.run_recipe(recipe.name)

        current_minute = time.strftime("%H:%M")
        if self._last_schedule_check != current_minute:
            self._last_schedule_check = current_minute
            event = TriggerEvent(type="schedule", data={})
            for recipe in self._agent.matching_recipes(event):
                await self._agent.run_recipe(recipe.name)

        if frame.idle_seconds > 0:
            event = TriggerEvent(type="idle", data={"idle_seconds": frame.idle_seconds})
            for recipe in self._agent.matching_recipes(event):
                await self._agent.run_recipe(recipe.name)

        if time.time() - self._last_discovery > 300:
            self._last_discovery = time.time()
            self._agent.discover_patterns()

    def _handle_signal(self, signum, _frame):
        logger.info("Signal %s received", signum)
        self._running = False

    def status(self):
        return self._agent.status

    def _acquire_instance_lock(self) -> None:
        self._lock_file.parent.mkdir(parents=True, exist_ok=True)
        handle = self._lock_file.open("a+")
        os.chmod(self._lock_file, 0o600)
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.close()
            raise RuntimeError("A PHANTOM daemon is already running for this user") from exc
        self._lock_handle = handle

    def _release_instance_lock(self) -> None:
        if self._lock_handle is None:
            return
        try:
            fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._lock_handle.close()
            self._lock_handle = None

    def _write_pid(self):
        self._pid_file.parent.mkdir(parents=True, exist_ok=True)
        self._pid_file.write_text(str(os.getpid()))
        os.chmod(self._pid_file, 0o600)

    def _cleanup_pid(self):
        if self._pid_file.exists():
            self._pid_file.unlink(missing_ok=True)

    def _cleanup_control_socket(self) -> None:
        if self._socket_path.exists():
            self._socket_path.unlink(missing_ok=True)
