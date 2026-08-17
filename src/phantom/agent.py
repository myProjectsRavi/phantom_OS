"""PhantomAgent — the main API."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

from phantom.config import PhantomConfig
from phantom.events import EventBus, PhantomEvents
from phantom.models import (
    ActionRequest,
    ActionResult,
    ActionType,
    IntentResult,
    LearnedPattern,
    PerceptionFrame,
    PhantomActionType,
    PredictedAction,
    Recipe,
    TriggerEvent,
    TrustLevel,
    UserAction,
)

logger = logging.getLogger("phantom")


class PhantomAgent:
    """The PHANTOM main API — invisible AI agent."""

    def __init__(self, config: PhantomConfig | None = None):
        """Initialize runtime engines, safety controls, recipes, and optional integrations.

        Heavy subsystem imports are deferred to reduce startup time and RAM usage.
        On an 8 GB device ``phantom --help`` and ``phantom doctor`` never load
        numpy, Pillow, or mss.
        """
        self.config = config or PhantomConfig.load()
        self.event_bus = EventBus()

        # Lazy imports — heavy subsystems loaded here, not at module level
        from phantom.actions.executor import ActionExecutor
        from phantom.automation.recipes import RecipeLibrary
        from phantom.automation.runner import RecipeRunner
        from phantom.automation.triggers import TriggerEngine
        from phantom.integrations.local_llm_bridge import LocalLLMBridge
        from phantom.integrations.neurovault_bridge import NeurovaultBridge
        from phantom.intent.recognizer import IntentRecognizer
        from phantom.patterns.discovery import PatternDiscovery
        from phantom.patterns.recorder import ActionRecorder
        from phantom.perception.engine import PerceptionEngine
        from phantom.prediction.engine import PredictionEngine
        from phantom.safety.emergency import EmergencyStop
        from phantom.safety.policy import SafetyPolicy

        # Perception
        self._perception = PerceptionEngine(self.config)

        # Intent
        self._intent = IntentRecognizer()

        # Patterns
        self._recorder = ActionRecorder()
        self._discovery = PatternDiscovery()
        self._patterns: dict[str, LearnedPattern] = {}
        self._load_patterns()

        # Prediction
        self._prediction = PredictionEngine()

        # Actions
        self._safety = SafetyPolicy(
            blocked_apps=self.config.excluded_apps,
            blocked_domains=self.config.blocked_domains,
            max_actions_per_minute=self.config.max_actions_per_minute,
        )
        self._safety.trust_level = TrustLevel(self.config.trust_level)
        self._executor = ActionExecutor(self._safety, self.event_bus)
        self._emergency = EmergencyStop(self._safety)

        # Automation
        self._recipes = RecipeLibrary(self.config.recipe_dir)
        self._recipes.load_from_disk()
        self._triggers = TriggerEngine(self._recipes)
        self._runner = RecipeRunner(self._executor, self.event_bus)

        # Optional public integrations
        neurovault_base = self.config.neurovault_base_dir or None
        self._neurovault = (
            NeurovaultBridge("phantom", base_dir=neurovault_base)
            if self.config.neurovault_enabled
            else None
        )
        self._local_llm_helpers = (
            LocalLLMBridge(config=self.config) if self.config.local_llm_helpers_enabled else None
        )

        # State
        self._running = False
        self._last_frame: Optional[PerceptionFrame] = None
        self._last_intent: Optional[IntentResult] = None
        self._stats: dict[str, float | int] = {
            "frames_processed": 0,
            "actions_executed": 0,
            "patterns_discovered": 0,
            "recipes_run": 0,
            "started_at": 0.0,
        }

        self._setup_logging()
        logger.info(
            "PhantomAgent initialized | Trust: %s | Recipes: %s",
            self.config.trust_level,
            len(self._recipes.list_recipes()),
        )

    @classmethod
    def init(cls, config_path=None):
        """Create an agent from a specific config file path."""
        return cls(PhantomConfig.load(config_path))

    @classmethod
    def open(cls):
        """Open an agent using the default local configuration."""
        return cls()

    # ── Lifecycle ──────────────────────────────

    def start(self):
        """Start runtime processing and publish a daemon-started event."""
        self._running = True
        self._stats["started_at"] = time.time()
        self.event_bus.emit(PhantomEvents.DAEMON_STARTED)
        logger.info("PHANTOM started")

    def stop(self):
        """Stop runtime processing and publish a daemon-stopped event."""
        self._running = False
        self._save_patterns()
        self.event_bus.emit(PhantomEvents.DAEMON_STOPPED)
        logger.info("PHANTOM stopped")

    def pause(self):
        """Temporarily pause processing without resetting state."""
        self._running = False

    def resume(self):
        """Resume processing after a pause."""
        self._running = True

    @property
    def is_running(self):
        """Return whether the agent run loop is currently active."""
        return self._running

    @property
    def status(self):
        """Return a structured snapshot of runtime status and integrations."""
        return {
            "running": self._running,
            "trust_level": self._safety.trust_level.value,
            "emergency_stopped": self._safety.is_stopped,
            "stats": self._stats,
            "current_app": self._last_frame.app_name if self._last_frame else None,
            "current_intent": self._last_intent.intent.value if self._last_intent else None,
            "recipes": len(self._recipes.list_recipes()),
            "patterns": len(self._patterns),
            "neurovault": bool(self._neurovault and self._neurovault.available),
            "local_llm_helpers": bool(
                self._local_llm_helpers and self._local_llm_helpers.available
            ),
            "llm_provider": self._get_llm_provider_name(),
        }

    # ── Perception ──────────────────────────────

    def perceive(self) -> Optional[PerceptionFrame]:
        """Capture and process one perception frame from the active desktop state."""
        frame = self._perception.perceive()
        if frame:
            self._stats["frames_processed"] += 1
            self.event_bus.emit(
                PhantomEvents.FRAME_PROCESSED,
                {
                    "app": frame.app_name,
                    "screen": frame.screen_type,
                },
            )

            # Detect app switch
            if self._last_frame and frame.app_name != self._last_frame.app_name:
                self.event_bus.emit(
                    PhantomEvents.APP_SWITCHED,
                    {
                        "from": self._last_frame.app_name,
                        "to": frame.app_name,
                    },
                )
                action = UserAction(
                    type=ActionType.APP_SWITCH,
                    app_name=frame.app_name,
                    data={"from": self._last_frame.app_name},
                )
                self._recorder.record(action)
                self._intent.add_action(action)
                self._prediction.observe(action)

            self._last_frame = frame
        return frame

    def get_active_app(self):
        """Return active app metadata from the last processed frame."""
        if self._last_frame:
            return {
                "name": self._last_frame.app_name,
                "window": self._last_frame.window_title,
                "screen": self._last_frame.screen_type,
            }
        return None

    # ── Intent ──────────────────────────────────

    def current_intent(self) -> Optional[IntentResult]:
        """Infer the current user intent from the latest available frame."""
        if self._last_frame:
            self._last_intent = self._intent.recognize(self._last_frame)
            self.event_bus.emit(
                PhantomEvents.INTENT_DETECTED,
                {
                    "intent": self._last_intent.intent.value,
                    "confidence": self._last_intent.confidence,
                },
            )
            return self._last_intent
        return None

    # ── Patterns ────────────────────────────────

    def learned_patterns(self) -> list[LearnedPattern]:
        """Return all currently learned user behavior patterns."""
        return list(self._patterns.values())

    def discover_patterns(self):
        """Analyze recent actions and add newly discovered reusable patterns."""
        actions = self._recorder.get_recent(500)
        if len(actions) < 10:
            return []
        new = self._discovery.analyze(actions)
        dirty = False
        for p in new:
            if p.signature not in self._patterns:
                self._patterns[p.signature] = p
                dirty = True
                self._stats["patterns_discovered"] += 1
                self.event_bus.emit(
                    PhantomEvents.PATTERN_DISCOVERED,
                    {
                        "name": p.name,
                        "frequency": p.frequency,
                    },
                )
                if self._neurovault and self._neurovault.available:
                    self._neurovault.store_pattern(
                        p.name or p.signature,
                        {
                            "signature": p.signature,
                            "frequency": p.frequency,
                            "confidence": p.confidence,
                            "steps": p.steps,
                        },
                    )
        if dirty:
            self._save_patterns()
        return new

    def approve_pattern(self, pattern_id: str):
        """Mark a learned pattern as approved for future automation use."""
        for p in self._patterns.values():
            if p.id == pattern_id:
                p.approved = True
                self.event_bus.emit(PhantomEvents.PATTERN_APPROVED, {"id": pattern_id})
                self._save_patterns()
                break

    def _pattern_store_path(self) -> Path:
        return Path(self.config.pattern_store).expanduser()

    def _load_patterns(self) -> None:
        path = self._pattern_store_path()
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load patterns (%s): %s", path, exc)
            return

        patterns: list[dict]
        if isinstance(payload, list):
            patterns = payload
        else:
            patterns = payload.get("patterns", []) if isinstance(payload, dict) else []

        loaded = 0
        for item in patterns:
            if not isinstance(item, dict):
                continue
            pattern = self._deserialize_pattern(item)
            if not pattern.signature:
                continue
            self._patterns[pattern.signature] = pattern
            loaded += 1
        if loaded:
            logger.info("Loaded %s patterns from %s", loaded, path)

    def _save_patterns(self) -> None:
        """Persist patterns to disk using atomic write to prevent corruption."""
        path = self._pattern_store_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "phantom.patterns.v1",
            "saved_at": int(time.time()),
            "patterns": [self._serialize_pattern(p) for p in self._patterns.values()],
        }
        try:
            # Atomic write: write to temp file then rename
            content = json.dumps(payload, indent=2, sort_keys=True)
            fd, tmp_path = tempfile.mkstemp(
                dir=path.parent,
                prefix=".patterns_",
                suffix=".tmp",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())
                # Atomic rename (POSIX guarantees atomicity for same-filesystem rename)
                Path(tmp_path).replace(path)
            except Exception:
                # Clean up temp file on failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to persist patterns (%s): %s", path, exc)

    @staticmethod
    def _serialize_pattern(pattern: LearnedPattern) -> dict:
        return {
            "id": pattern.id,
            "name": pattern.name,
            "signature": pattern.signature,
            "steps": pattern.steps,
            "frequency": pattern.frequency,
            "confidence": pattern.confidence,
            "last_seen": pattern.last_seen,
            "created_at": pattern.created_at,
            "approved": pattern.approved,
            "auto_execute": pattern.auto_execute,
            "tags": list(pattern.tags),
        }

    @staticmethod
    def _deserialize_pattern(payload: dict) -> LearnedPattern:
        return LearnedPattern(
            id=str(payload.get("id", "")),
            name=str(payload.get("name", "")),
            signature=str(payload.get("signature", "")),
            steps=list(payload.get("steps", [])),
            frequency=int(payload.get("frequency", 0)),
            confidence=float(payload.get("confidence", 0.0)),
            last_seen=float(payload.get("last_seen", 0.0)),
            created_at=float(payload.get("created_at", time.time())),
            approved=bool(payload.get("approved", False)),
            auto_execute=bool(payload.get("auto_execute", False)),
            tags=[str(tag) for tag in payload.get("tags", [])],
        )

    # ── Predictions ─────────────────────────────

    def predictions(self) -> list[PredictedAction]:
        """Return predicted next user actions based on recent behavior."""
        return self._prediction.predict()

    # ── Actions ──────────────────────────────────

    async def execute(self, action: ActionRequest) -> ActionResult:
        """Execute one action request through the authoritative safety boundary."""
        result = await self._executor.execute(action)
        if result.success:
            self._stats["actions_executed"] += 1
        return result

    @staticmethod
    def _run_async(coro):
        """Run an async coroutine in a synchronous API surface."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        # When called inside an existing event loop, run the coroutine in
        # a dedicated thread with its own loop.
        result_holder: dict[str, object] = {}
        error_holder: dict[str, BaseException] = {}

        def _runner() -> None:
            try:
                result_holder["value"] = asyncio.run(coro)
            except BaseException as exc:  # noqa: BLE001
                error_holder["error"] = exc

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join()

        if "error" in error_holder:
            raise error_holder["error"]
        return result_holder.get("value")

    def type_text(self, text):
        """Type text through the action executor."""
        return self._run_async(
            self.execute(ActionRequest(type=PhantomActionType.TYPE_TEXT, params={"text": text}))
        )

    def activate_app(self, app):
        """Activate an application by name."""
        return self._run_async(
            self.execute(ActionRequest(type=PhantomActionType.APP_ACTIVATE, params={"app": app}))
        )

    def open_url(self, url):
        """Open a URL using the action executor."""
        return self._run_async(
            self.execute(ActionRequest(type=PhantomActionType.URL_OPEN, params={"url": url}))
        )

    def clipboard_get(self):
        """Read current clipboard text."""
        return self._executor.clipboard.get()

    def clipboard_set(self, content):
        """Write content to the clipboard."""
        self._executor.clipboard.set(content)

    def clipboard_history(self, limit=20):
        """Return recent clipboard history entries."""
        return self._executor.clipboard.history(limit)

    def undo(self):
        """Undo the last reversible action if available."""
        return self._executor.undo_last()

    # ── Recipes ──────────────────────────────────

    def list_recipes(self):
        """Return all recipes currently available to the agent."""
        return self._recipes.list_recipes()

    def matching_recipes(self, event: TriggerEvent) -> list[Recipe]:
        """Return enabled recipes whose triggers match a trigger event."""
        return self._triggers.check(event)

    async def run_recipe(self, name, variables=None):
        """Execute a recipe by name with optional runtime variables."""
        recipe = self._recipes.get(name)
        if not recipe:
            return {"error": f"Recipe not found: {name}"}
        result = await self._runner.run(recipe, variables)
        self._stats["recipes_run"] += 1
        if result.get("success") and self._neurovault and self._neurovault.available:
            self._neurovault.store_workflow(recipe.name, [s.type for s in recipe.steps])
        return result

    def create_recipe(self, name, steps):
        """Create and persist a user-defined recipe from step definitions."""
        from phantom.models import RecipeStep

        recipe = Recipe(name=name, steps=[RecipeStep(**s) for s in steps], source="user")
        self._recipes.add(recipe)
        self._recipes.save(recipe)
        return recipe

    def enable_recipe(self, name):
        """Enable a recipe so its trigger can run."""
        r = self._recipes.get(name)
        if r:
            r.enabled = True

    def disable_recipe(self, name):
        """Disable a recipe so it no longer runs on trigger."""
        r = self._recipes.get(name)
        if r:
            r.enabled = False

    # ── Safety ────────────────────────────────────

    def set_trust_level(self, level: TrustLevel):
        """Set safety trust level and emit a trust-change event."""
        self._safety.trust_level = level
        self.event_bus.emit(PhantomEvents.TRUST_CHANGED, {"level": level.value})

    def emergency_stop(self):
        """Immediately stop all future actions via safety circuit."""
        self._safety.emergency_stop()
        self.event_bus.emit(PhantomEvents.EMERGENCY_STOP)

    @property
    def trust_level(self):
        """Return the current safety trust level."""
        return self._safety.trust_level

    def action_history(self, limit=50):
        """Return the most recent executed actions up to a limit."""
        return self._executor._history[-limit:]

    @property
    def neurovault(self):
        """Expose active NeuroVault bridge instance when configured."""
        return self._neurovault

    @property
    def local_llm_helpers(self):
        """Expose optional local-LLM helper bridge when configured."""
        return self._local_llm_helpers

    @property
    def llm(self):
        """Expose active LLM provider for direct use."""
        from phantom.llm import get_provider

        return get_provider(self.config)

    def _get_llm_provider_name(self) -> str:
        """Return the name of the active LLM provider."""
        try:
            from phantom.llm import get_provider

            provider = get_provider(self.config)
            return provider.name if provider.available() else "none"
        except Exception:
            return "none"

    # ── Observability ─────────────────────────────

    def stats(self):
        """Return runtime counters including derived uptime."""
        uptime = time.time() - self._stats["started_at"] if self._stats["started_at"] else 0
        return {**self._stats, "uptime_seconds": uptime}

    @property
    def frame_interval(self) -> float:
        """Return current perception polling interval in seconds."""
        return self._perception.frame_interval

    def _setup_logging(self):
        """Initialize module-level logging with both console and file output.

        Configures:
        - Console handler for immediate feedback
        - Rotating file handler for persistent logs (10MB max, 5 backups)
        """
        from logging.handlers import RotatingFileHandler

        level = getattr(logging, self.config.log_level.upper(), logging.INFO)
        phantom_logger = logging.getLogger("phantom")
        phantom_logger.setLevel(level)

        # Clear any existing handlers to avoid duplicates
        phantom_logger.handlers.clear()

        formatter = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        phantom_logger.addHandler(console_handler)

        # File handler with rotation
        log_dir = Path(self.config.pattern_store).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "phantom.log"

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        phantom_logger.addHandler(file_handler)

        # Prevent propagation to root logger
        phantom_logger.propagate = False
