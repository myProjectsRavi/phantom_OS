"""Tests for LLM provider router."""

from __future__ import annotations

from unittest.mock import patch

from phantom.config import PhantomConfig
from phantom.llm.provider import NullProvider
from phantom.llm.router import get_provider, reset_cache


class TestRouter:
    def setup_method(self):
        reset_cache()

    def teardown_method(self):
        reset_cache()

    def test_none_provider_returns_null(self):
        provider = get_provider(PhantomConfig(llm_provider="none"))
        assert isinstance(provider, NullProvider)

    @patch("phantom.llm.router._make_ollama")
    def test_auto_picks_ollama_when_available(self, mock_make):
        from phantom.llm.ollama import OllamaProvider

        mock_provider = OllamaProvider.__new__(OllamaProvider)
        mock_provider._host = "http://localhost:11434"
        mock_provider._model_pref = "auto"
        mock_provider._timeout_connect = 5.0
        mock_provider._timeout_read = 30.0
        mock_provider._resolved_model = None
        mock_make.return_value = mock_provider

        with patch.object(mock_provider, "available", return_value=True):
            provider = get_provider(PhantomConfig(llm_provider="auto"))
            assert provider is mock_provider

    @patch("phantom.llm.router._make_ollama")
    def test_auto_falls_back_to_null(self, mock_make):
        mock_provider = NullProvider()
        mock_make.return_value = mock_provider

        with patch.object(mock_provider, "available", return_value=False):
            provider = get_provider(PhantomConfig(llm_provider="auto"))
            assert isinstance(provider, NullProvider)

    def test_identical_configuration_reuses_cache(self):
        config = PhantomConfig(llm_provider="none")
        first = get_provider(config)
        second = get_provider(config)
        assert first is second

    @patch("phantom.llm.router._discover")
    def test_different_configuration_invalidates_cache(self, discover):
        first_provider = NullProvider()
        second_provider = NullProvider()
        discover.side_effect = [first_provider, second_provider]

        first = get_provider(PhantomConfig(llm_provider="none", llm_model="model-a"))
        second = get_provider(PhantomConfig(llm_provider="none", llm_model="model-b"))

        assert first is first_provider
        assert second is second_provider
        assert discover.call_count == 2

    def test_unknown_provider_returns_null(self):
        provider = get_provider(PhantomConfig(llm_provider="nonexistent_thing"))
        assert isinstance(provider, NullProvider)
