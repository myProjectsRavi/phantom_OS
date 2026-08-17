"""Ollama LLM provider — stdlib only, zero external dependencies."""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from typing import Optional

from phantom.llm.provider import LLMProvider, LLMResponse

logger = logging.getLogger("phantom.llm.ollama")

# Preferred small models for 8GB RAM devices, ordered by preference.
_PREFERRED_MODELS = [
    "qwen2.5:1.5b",
    "qwen2.5:0.5b",
    "phi3:mini",
    "llama3.2:1b",
    "gemma2:2b",
    "tinyllama",
]


class OllamaProvider(LLMProvider):
    """Ollama local LLM provider using only urllib."""

    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "auto",
        timeout_connect: float = 5.0,
        timeout_read: float = 30.0,
    ):
        self._host = host.rstrip("/")
        self._model_pref = model
        self._timeout_connect = timeout_connect
        self._timeout_read = timeout_read
        self._resolved_model: Optional[str] = None

    @property
    def name(self) -> str:
        return "ollama"

    def available(self) -> bool:
        """Check if Ollama server is reachable."""
        try:
            self._http_get(f"{self._host}/api/tags", timeout=self._timeout_connect)
            return True
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """List models available on the Ollama server."""
        try:
            data = self._http_get(f"{self._host}/api/tags", timeout=self._timeout_connect)
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    @property
    def model(self) -> str:
        """Return the resolved model name."""
        if self._resolved_model is None:
            self._resolved_model = self._pick_model()
        return self._resolved_model

    def _pick_model(self) -> str:
        """Pick the best model for this device."""
        if self._model_pref != "auto":
            return self._model_pref

        available = self.list_models()
        if not available:
            return "qwen2.5:1.5b"

        for preferred in _PREFERRED_MODELS:
            for avail in available:
                if avail == preferred or avail.startswith(preferred):
                    return avail
        return available[0]

    async def complete(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, self._http_post, f"{self._host}/api/chat", payload, self._timeout_read
        )
        content = ""
        if "message" in data:
            content = data["message"].get("content", "")
        elif "response" in data:
            content = data["response"]
        return LLMResponse(
            content=content,
            model=data.get("model", self.model),
            usage={
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
            },
        )

    async def embed(self, text: str) -> list[float]:
        payload = {"model": self.model, "prompt": text}
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, self._http_post, f"{self._host}/api/embeddings", payload, self._timeout_read
        )
        return data.get("embedding", [])

    @staticmethod
    def _http_get(url: str, timeout: float) -> dict:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())

    @staticmethod
    def _http_post(url: str, data: dict, timeout: float) -> dict:
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
