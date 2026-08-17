"""Tests for LLM provider abstractions."""

from __future__ import annotations

import asyncio

import pytest

from phantom.llm.provider import LLMProvider, LLMResponse, NullProvider


class TestLLMResponse:
    def test_defaults(self):
        r = LLMResponse()
        assert r.content == ""
        assert r.model == ""
        assert r.usage == {}

    def test_custom_values(self):
        r = LLMResponse(content="hello", model="test", usage={"tokens": 5})
        assert r.content == "hello"
        assert r.model == "test"
        assert r.usage == {"tokens": 5}


class TestNullProvider:
    def test_name(self):
        p = NullProvider()
        assert p.name == "none"

    def test_not_available(self):
        p = NullProvider()
        assert p.available() is False

    def test_no_models(self):
        p = NullProvider()
        assert p.list_models() == []

    def test_complete_returns_empty(self):
        p = NullProvider()
        result = asyncio.run(p.complete("test prompt"))
        assert isinstance(result, LLMResponse)
        assert result.content == ""

    def test_embed_raises(self):
        p = NullProvider()
        with pytest.raises(NotImplementedError):
            asyncio.run(p.embed("test"))


class TestLLMProviderABC:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            LLMProvider()
