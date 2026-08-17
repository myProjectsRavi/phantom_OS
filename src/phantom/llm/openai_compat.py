"""OpenAI-compatible LLM provider for LM Studio, vLLM, llama.cpp server, etc."""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request

from phantom.llm.provider import LLMProvider, LLMResponse

logger = logging.getLogger("phantom.llm.openai_compat")


class OpenAICompatProvider(LLMProvider):
    """Generic OpenAI-compatible API provider using only urllib."""

    def __init__(
        self,
        base_url: str = "http://localhost:1234",
        model: str = "",
        api_key: str = "",
        timeout: float = 30.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "openai_compat"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def available(self) -> bool:
        try:
            req = urllib.request.Request(
                f"{self._base_url}/v1/models", headers=self._headers()
            )
            with urllib.request.urlopen(req, timeout=5.0):
                return True
        except Exception:
            return False

    def list_models(self) -> list[str]:
        try:
            req = urllib.request.Request(
                f"{self._base_url}/v1/models", headers=self._headers()
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode())
                return [m["id"] for m in data.get("data", [])]
        except Exception:
            return []

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
        model = self._model or (self.list_models() or ["default"])[0]
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self._base_url}/v1/chat/completions",
            data=body,
            headers=self._headers(),
            method="POST",
        )
        loop = asyncio.get_event_loop()

        def _do_request():
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode())

        data = await loop.run_in_executor(None, _do_request)
        content = ""
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
        return LLMResponse(
            content=content,
            model=data.get("model", model),
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
            },
        )
