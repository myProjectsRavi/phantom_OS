"""LLM provider auto-discovery and routing."""

from __future__ import annotations

import logging
from typing import Optional

from phantom.llm.provider import LLMProvider, NullProvider

logger = logging.getLogger("phantom.llm.router")

_cached_provider: Optional[LLMProvider] = None
_cached_key: tuple[object, ...] | None = None


def _config_key(config) -> tuple[object, ...]:
    if config is None:
        return ("default",)
    return (
        getattr(config, "llm_provider", "auto"),
        getattr(config, "ollama_host", "http://localhost:11434"),
        getattr(config, "llm_model", "auto"),
        getattr(config, "llm_timeout", 30.0),
        getattr(config, "llm_base_url", ""),
        getattr(config, "llm_api_key", ""),
    )


def get_provider(config=None) -> LLMProvider:
    """Return the best available LLM provider for the exact configuration."""
    global _cached_key, _cached_provider
    key = _config_key(config)
    if _cached_provider is not None and _cached_key == key:
        return _cached_provider

    provider = _discover(config)
    _cached_provider = provider
    _cached_key = key
    return provider


def reset_cache() -> None:
    global _cached_key, _cached_provider
    _cached_provider = None
    _cached_key = None


def _discover(config) -> LLMProvider:
    if config is None:
        from phantom.config import PhantomConfig

        config = PhantomConfig()
    pref = getattr(config, "llm_provider", "auto")
    if pref == "none":
        return NullProvider()
    if pref == "ollama":
        return _make_ollama(config)
    if pref == "openai_compat":
        return _make_openai_compat(config)
    if pref == "auto":
        ollama = _make_ollama(config)
        if ollama.available():
            return ollama
        base_url = getattr(config, "llm_base_url", "")
        if base_url:
            compat = _make_openai_compat(config)
            if compat.available():
                return compat
        return NullProvider()
    logger.warning("Unknown LLM provider '%s', falling back to none", pref)
    return NullProvider()


def _make_ollama(config) -> LLMProvider:
    from phantom.llm.ollama import OllamaProvider

    return OllamaProvider(
        host=getattr(config, "ollama_host", "http://localhost:11434"),
        model=getattr(config, "llm_model", "auto"),
        timeout_connect=5.0,
        timeout_read=getattr(config, "llm_timeout", 30.0),
    )


def _make_openai_compat(config) -> LLMProvider:
    from phantom.llm.openai_compat import OpenAICompatProvider

    return OpenAICompatProvider(
        base_url=getattr(config, "llm_base_url", "http://localhost:1234"),
        model=getattr(config, "llm_model", ""),
        api_key=getattr(config, "llm_api_key", ""),
        timeout=getattr(config, "llm_timeout", 30.0),
    )
