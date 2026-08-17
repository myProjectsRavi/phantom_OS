"""Tests for OpenAI-compatible LLM provider."""

from __future__ import annotations

import asyncio
import json
import urllib.error
from unittest.mock import MagicMock, patch

from phantom.llm.openai_compat import OpenAICompatProvider


def _mock_urlopen(response_data):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_data).encode()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


class TestOpenAICompatAvailable:
    @patch("phantom.llm.openai_compat.urllib.request.urlopen")
    def test_available_when_endpoint_responds(self, mock_open):
        mock_open.return_value = _mock_urlopen({"data": []})
        p = OpenAICompatProvider(base_url="http://localhost:1234")
        assert p.available() is True

    @patch("phantom.llm.openai_compat.urllib.request.urlopen")
    def test_not_available_on_error(self, mock_open):
        mock_open.side_effect = urllib.error.URLError("refused")
        p = OpenAICompatProvider()
        assert p.available() is False


class TestOpenAICompatListModels:
    @patch("phantom.llm.openai_compat.urllib.request.urlopen")
    def test_returns_model_ids(self, mock_open):
        mock_open.return_value = _mock_urlopen({"data": [{"id": "model-a"}, {"id": "model-b"}]})
        p = OpenAICompatProvider()
        assert p.list_models() == ["model-a", "model-b"]


class TestOpenAICompatComplete:
    @patch("phantom.llm.openai_compat.urllib.request.urlopen")
    def test_complete_parses_response(self, mock_open):
        # model is set explicitly so list_models is NOT called — only one urlopen
        mock_open.return_value = _mock_urlopen(
            {
                "model": "test-model",
                "choices": [{"message": {"content": "Hi there"}}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 3},
            }
        )

        p = OpenAICompatProvider(model="test-model")
        result = asyncio.run(p.complete("Hello"))

        assert result.content == "Hi there"
        assert result.model == "test-model"

    @patch("phantom.llm.openai_compat.urllib.request.urlopen")
    def test_api_key_header_included(self, mock_open):
        mock_open.return_value = _mock_urlopen(
            {
                "choices": [{"message": {"content": "ok"}}],
            }
        )

        p = OpenAICompatProvider(model="m", api_key="test-api-key-123")
        asyncio.run(p.complete("test"))

        req = mock_open.call_args[0][0]
        assert req.get_header("Authorization") == "Bearer test-api-key-123"

    def test_name(self):
        p = OpenAICompatProvider()
        assert p.name == "openai_compat"
