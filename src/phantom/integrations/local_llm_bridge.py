"""Optional higher-level helpers backed only by PhantomOS local LLM providers."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any, Optional

from phantom.models import (
    ActionRequest,
    IntentResult,
    PerceptionFrame,
    PhantomActionType,
    Recipe,
    RecipeStep,
    RecipeTrigger,
)

logger = logging.getLogger("phantom.local_llm_helpers")


class LocalLLMBridge:
    """Use PhantomOS's configured local LLM provider for optional helpers."""

    def __init__(self, config=None):
        self._provider: Optional[Any] = None
        self._config = config
        self._init()

    def _init(self):
        try:
            from phantom.llm import get_provider

            provider = get_provider(self._config)
            if provider.available():
                self._provider = provider
                logger.info("Local LLM helper provider connected: %s", provider.name)
                return
        except Exception as exc:  # noqa: BLE001
            logger.debug("Local LLM helper provider init failed: %s", exc)

        logger.info("No local LLM helper provider available; rule-based decisions remain active")

    @property
    def available(self) -> bool:
        return self._provider is not None

    async def _complete(self, prompt: str, system: str = "", temperature: float = 0.3):
        if not self._provider:
            raise RuntimeError("No LLM provider available")
        response = await self._provider.complete(prompt, system=system, temperature=temperature)
        return SimpleNamespace(content=response.content)

    async def disambiguate_intent(
        self, frame: PerceptionFrame, candidates: list[IntentResult]
    ) -> IntentResult:
        """Use the configured local LLM provider to resolve ambiguous intent."""
        if not self.available or not candidates:
            return candidates[0] if candidates else IntentResult()

        context = (
            f"App: {frame.app_name} ({frame.screen_type})\n"
            f"Window: {frame.window_title}\n"
            f"Candidates: {', '.join(f'{c.intent.value}({c.confidence:.2f})' for c in candidates)}\n"
            "Which intent? Return ONLY the intent name."
        )
        try:
            response = await self._complete(
                context,
                system="You classify user intent. Return only the intent type name.",
            )
            chosen = response.content.strip().lower()
            for candidate in candidates:
                if candidate.intent.value in chosen:
                    candidate.confidence = min(1.0, candidate.confidence + 0.15)
                    return candidate
        except Exception as exc:  # noqa: BLE001
            logger.warning("Intent disambiguation failed: %s", exc)
        return candidates[0]

    async def generate_recipe(self, description: str) -> Recipe:
        """Generate a candidate recipe through the configured local LLM provider."""
        if not self.available:
            raise RuntimeError("No LLM provider available")

        prompt = (
            f"Create a PHANTOM automation recipe for: {description}\n"
            "Actions: type_text, press_key, clipboard_copy, clipboard_paste, "
            "app_activate, url_open, file_open, run_command, wait, notification\n"
            "Return JSON: {name, description, trigger:{type,config}, "
            "steps:[{type,params,delay_after}]}"
        )
        response = await self._complete(
            prompt,
            system="Return valid JSON only.",
            temperature=0.3,
        )
        data = self._parse_json(response.content)
        return Recipe(
            name=data.get("name", "generated"),
            description=data.get("description", description),
            trigger=RecipeTrigger(**data["trigger"]) if "trigger" in data else None,
            steps=[RecipeStep(**step) for step in data.get("steps", [])],
            source="generated",
        )

    async def suggest_action(
        self, frame: PerceptionFrame, intent: IntentResult
    ) -> Optional[ActionRequest]:
        """Suggest one candidate action without bypassing the executor safety boundary."""
        if not self.available:
            return None
        prompt = (
            f"User in {frame.app_name} ({frame.screen_type}), intent: {intent.intent.value}\n"
            "Suggest ONE helpful action as JSON: {type, params, reason}"
        )
        try:
            response = await self._complete(
                prompt,
                system="You are PHANTOM. Suggest ONE action.",
                temperature=0.2,
            )
            data = self._parse_json(response.content)
            return ActionRequest(
                type=PhantomActionType(data["type"]),
                params=data.get("params", {}),
                source="local_llm",
            )
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Parse plain or fenced JSON response payloads."""
        payload = text.strip()
        if payload.startswith("```"):
            lines = payload.splitlines()
            if lines:
                lines = lines[1:]
            if lines and lines[0].strip().lower() == "json":
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            payload = "\n".join(lines).strip()
        return json.loads(payload)
