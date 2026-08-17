"""NEUROVAULT integration - pattern knowledge enrichment."""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("phantom.neurovault")

try:
    from neurovault.engine import NeurovaultEngine

    HAS_NEUROVAULT = True
except ImportError:  # pragma: no cover
    HAS_NEUROVAULT = False


class NeurovaultBridge:
    """Integrate PHANTOM with NEUROVAULT for cognitive memory."""

    def __init__(self, vault_name: str = "phantom", base_dir: str | None = None):
        """Initialize and connect to a NEUROVAULT engine when available."""
        self._vault_name = vault_name
        self._base_dir = base_dir
        self._vault: Optional[Any] = None
        self._init()

    def _init(self):
        if not HAS_NEUROVAULT:
            logger.info("NEUROVAULT not available - operating without cognitive memory")
            return
        kwargs_list = []
        if self._base_dir:
            kwargs_list.append({"base_dir": self._base_dir})
        kwargs_list.append({})

        for kwargs in kwargs_list:
            try:
                self._vault = NeurovaultEngine.open(self._vault_name, **kwargs)
                logger.info("NEUROVAULT connected: %s", self._vault_name)
                return
            except Exception:
                continue

        for kwargs in kwargs_list:
            try:
                self._vault = NeurovaultEngine.init(self._vault_name, **kwargs)
                logger.info("NEUROVAULT connected: %s", self._vault_name)
                return
            except Exception as exc:
                if "already exists" in str(exc).lower():
                    try:
                        self._vault = NeurovaultEngine.open(self._vault_name, **kwargs)
                        logger.info("NEUROVAULT connected: %s", self._vault_name)
                        return
                    except Exception:
                        pass
                continue

        logger.warning("NEUROVAULT init failed for vault: %s", self._vault_name)
        self._vault = None

    @property
    def available(self) -> bool:
        """Return whether NEUROVAULT integration is currently active."""
        return self._vault is not None

    def store_pattern(self, pattern_name: str, pattern_data: dict):
        """Store a learned pattern as cognitive memory."""
        if not self._vault:
            return None
        try:
            return self._vault.ingest(
                content=f"Learned pattern: {pattern_name}",
                source="phantom.pattern",
                importance=float(pattern_data.get("confidence", 0.6)),
                metadata={
                    "pattern_name": pattern_name,
                    "pattern_data": pattern_data,
                    "tags": ["phantom", "pattern", pattern_name],
                },
            )
        except Exception as exc:
            logger.warning("Pattern store failed: %s", exc)
            return None

    def enrich_intent(self, app_name: str, screen_text: str) -> dict:
        """Retrieve related memories to enrich intent recognition."""
        if not self._vault:
            return {}
        try:
            query = f"phantom pattern {app_name} {screen_text[:120]}"
            results = self._vault.recall(query=query, limit=3, mode="multi")
        except Exception:
            return {}

        related: list[str] = []
        for row in results:
            memory = getattr(row, "memory", row)
            content = getattr(memory, "content", "")
            if content:
                related.append(str(content))
        return {
            "related_patterns": related,
            "context": f"Known activity in {app_name}" if related else "",
        }

    def search_patterns(self, query: str, limit: int = 5) -> list:
        """Search for similar patterns in NEUROVAULT."""
        if not self._vault:
            return []
        try:
            return self._vault.recall(query=f"phantom pattern {query}", limit=limit, mode="multi")
        except Exception:
            return []

    def store_workflow(self, workflow_name: str, steps: list):
        """Store a completed workflow for future reuse."""
        if not self._vault:
            return None
        try:
            return self._vault.ingest(
                content=f"Workflow: {workflow_name} ({len(steps)} steps)",
                source="phantom.workflow",
                importance=0.6,
                metadata={
                    "workflow_name": workflow_name,
                    "steps": steps,
                    "tags": ["phantom", "workflow"],
                },
            )
        except Exception as exc:
            logger.warning("Workflow store failed: %s", exc)
            return None
