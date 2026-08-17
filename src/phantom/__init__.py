"""PHANTOM package exports."""

from __future__ import annotations

from phantom.models import (
    ActionRequest,
    ActionResult,
    IntentResult,
    IntentType,
    LearnedPattern,
    PerceptionFrame,
    PredictedAction,
    Recipe,
    TrustLevel,
)

__version__ = "0.1.0"
__all__ = [
    "PhantomAgent",
    "PerceptionFrame",
    "IntentResult",
    "IntentType",
    "PredictedAction",
    "ActionRequest",
    "ActionResult",
    "LearnedPattern",
    "Recipe",
    "TrustLevel",
]


def __getattr__(name: str):
    if name == "PhantomAgent":
        try:
            from phantom.agent import PhantomAgent
        except ModuleNotFoundError as exc:  # pragma: no cover
            missing = getattr(exc, "name", "dependency")
            raise ImportError(
                f"PhantomAgent requires optional runtime dependency '{missing}'. "
                "Install project dependencies (for example: pip install -e .[dev])."
            ) from exc

        return PhantomAgent
    raise AttributeError(name)
