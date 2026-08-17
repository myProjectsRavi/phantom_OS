"""Security regression tests for LLM endpoint URL validation."""

from __future__ import annotations

import pytest

from phantom.llm.ollama import OllamaProvider
from phantom.llm.openai_compat import OpenAICompatProvider


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/model",
        "ftp://localhost/model",
        "custom://localhost/model",
        "localhost:11434",
        "http:///missing-host",
        "http://user:password@localhost:11434",
        "http://localhost:bad-port",
    ],
)
def test_ollama_rejects_non_http_or_credentialed_endpoints(url):
    with pytest.raises(ValueError):
        OllamaProvider(host=url)


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/api",
        "ftp://localhost/api",
        "custom://localhost/api",
        "localhost:1234",
        "https:///missing-host",
        "https://user:password@example.com",
        "https://example.com:bad-port",
    ],
)
def test_openai_compat_rejects_non_http_or_credentialed_endpoints(url):
    with pytest.raises(ValueError):
        OpenAICompatProvider(base_url=url)


def test_ollama_transport_helpers_revalidate_direct_urls():
    with pytest.raises(ValueError):
        OllamaProvider._http_get("file:///tmp/tags", timeout=1.0)
    with pytest.raises(ValueError):
        OllamaProvider._http_post("file:///tmp/chat", {}, timeout=1.0)


def test_valid_http_and_https_endpoints_are_accepted():
    assert OllamaProvider(host="http://localhost:11434")._host == "http://localhost:11434"
    assert (
        OpenAICompatProvider(base_url="https://api.example.com/v1")._base_url
        == "https://api.example.com/v1"
    )
