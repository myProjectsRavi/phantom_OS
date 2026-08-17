"""Abstract LLM provider interface."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    """Response from an LLM provider."""

    content: str = ""
    model: str = ""
    usage: dict = field(default_factory=dict)


class LLMProvider(abc.ABC):
    """Abstract base for LLM providers (Ollama, OpenAI-compat, etc.)."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Provider name for display."""

    @abc.abstractmethod
    def available(self) -> bool:
        """Check if provider is reachable."""

    @abc.abstractmethod
    def list_models(self) -> list[str]:
        """Return available model names."""

    @abc.abstractmethod
    async def complete(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Generate a completion."""

    async def embed(self, text: str) -> list[float]:
        """Generate embeddings (optional)."""
        raise NotImplementedError("Embeddings not supported by this provider")


class NullProvider(LLMProvider):
    """No-op provider when no LLM is available."""

    @property
    def name(self) -> str:
        return "none"

    def available(self) -> bool:
        return False

    def list_models(self) -> list[str]:
        return []

    async def complete(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        return LLMResponse()
