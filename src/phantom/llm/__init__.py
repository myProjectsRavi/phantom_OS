"""LLM provider abstraction — zero external dependencies."""

from __future__ import annotations

from phantom.llm.provider import LLMProvider, LLMResponse, NullProvider
from phantom.llm.router import get_provider

__all__ = ["LLMProvider", "LLMResponse", "NullProvider", "get_provider"]
