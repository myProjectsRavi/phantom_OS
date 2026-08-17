"""Tests for Ollama LLM provider."""

from __future__ import annotations

import asyncio
import json
import urllib.error
from unittest.mock import MagicMock, patch

from phantom.llm.ollama import OllamaProvider


def _mock_urlopen(response_data, status=200):
    """Create a mock for urllib.request.urlopen."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_data).encode()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


class TestOllamaAvailable:
    @patch("phantom.llm.ollama.urllib.request.urlopen")
    def test_available_when_server_responds(self, mock_open):
        mock_open.return_value = _mock_urlopen({"models": []})
        p = OllamaProvider()
        assert p.available() is True

    @patch("phantom.llm.ollama.urllib.request.urlopen")
    def test_not_available_on_connection_error(self, mock_open):
        mock_open.side_effect = urllib.error.URLError("refused")
        p = OllamaProvider()
        assert p.available() is False

    @patch("phantom.llm.ollama.urllib.request.urlopen")
    def test_not_available_on_timeout(self, mock_open):
        mock_open.side_effect = TimeoutError()
        p = OllamaProvider()
        assert p.available() is False


class TestOllamaListModels:
    @patch("phantom.llm.ollama.urllib.request.urlopen")
    def test_returns_model_names(self, mock_open):
        mock_open.return_value = _mock_urlopen(
            {"models": [{"name": "qwen2.5:1.5b"}, {"name": "llama3.2:1b"}]}
        )
        p = OllamaProvider()
        models = p.list_models()
        assert models == ["qwen2.5:1.5b", "llama3.2:1b"]

    @patch("phantom.llm.ollama.urllib.request.urlopen")
    def test_returns_empty_on_error(self, mock_open):
        mock_open.side_effect = urllib.error.URLError("down")
        p = OllamaProvider()
        assert p.list_models() == []


class TestOllamaPickModel:
    @patch("phantom.llm.ollama.urllib.request.urlopen")
    def test_prefers_qwen_small(self, mock_open):
        mock_open.return_value = _mock_urlopen(
            {"models": [{"name": "llama3.2:1b"}, {"name": "qwen2.5:1.5b"}]}
        )
        p = OllamaProvider(model="auto")
        assert p.model == "qwen2.5:1.5b"

    @patch("phantom.llm.ollama.urllib.request.urlopen")
    def test_falls_back_to_first_available(self, mock_open):
        mock_open.return_value = _mock_urlopen({"models": [{"name": "custom-model:latest"}]})
        p = OllamaProvider(model="auto")
        assert p.model == "custom-model:latest"

    def test_explicit_model_used_directly(self):
        p = OllamaProvider(model="my-model:7b")
        assert p.model == "my-model:7b"

    @patch("phantom.llm.ollama.urllib.request.urlopen")
    def test_default_when_no_models(self, mock_open):
        mock_open.return_value = _mock_urlopen({"models": []})
        p = OllamaProvider(model="auto")
        assert p.model == "qwen2.5:1.5b"


class TestOllamaComplete:
    @patch("phantom.llm.ollama.urllib.request.urlopen")
    def test_complete_parses_response(self, mock_open):
        # model is explicit — only one urlopen call for chat completion
        mock_open.return_value = _mock_urlopen(
            {
                "model": "qwen2.5:1.5b",
                "message": {"content": "Hello world"},
                "prompt_eval_count": 10,
                "eval_count": 5,
            }
        )

        p = OllamaProvider(model="qwen2.5:1.5b")
        result = asyncio.run(p.complete("Say hello", system="Be friendly"))

        assert result.content == "Hello world"
        assert result.model == "qwen2.5:1.5b"
        assert result.usage["prompt_tokens"] == 10
        assert result.usage["completion_tokens"] == 5

    @patch("phantom.llm.ollama.urllib.request.urlopen")
    def test_complete_sends_correct_payload(self, mock_open):
        mock_open.return_value = _mock_urlopen(
            {
                "model": "test",
                "message": {"content": "ok"},
            }
        )

        p = OllamaProvider(model="test", host="http://myhost:1234")
        asyncio.run(p.complete("prompt", system="sys", temperature=0.5, max_tokens=512))

        # Verify the POST was made
        call_args = mock_open.call_args
        req = call_args[0][0]
        assert "myhost:1234" in req.full_url
        body = json.loads(req.data)
        assert body["model"] == "test"
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][0]["content"] == "sys"
        assert body["messages"][1]["role"] == "user"
        assert body["options"]["temperature"] == 0.5
        assert body["options"]["num_predict"] == 512
