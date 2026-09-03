# src/llm_regress/providers/openai_compat.py
from __future__ import annotations

import asyncio
import json
import os

import httpx

from ..models import TargetConfig
from .base import ChatResponse, ProviderError


class OpenAICompatClient:
    """适配任何 OpenAI 兼容端点（DeepSeek / Qwen / Kimi / vLLM / Ollama…）。"""

    def __init__(
        self,
        config: TargetConfig,
        *,
        timeout: float = 60.0,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
        sleep=asyncio.sleep,
    ):
        self._base = config.base_url.rstrip("/")
        self._model = config.model
        self._key: str | None = None
        if config.api_key_env:
            self._key = os.environ.get(config.api_key_env)
            if not self._key:
                raise ProviderError(f"Environment variable {config.api_key_env} is not set")
        self._timeout = timeout
        self._max_retries = max_retries
        self._transport = transport
        self._sleep = sleep

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
    ) -> ChatResponse:
        payload = {
            "model": model or self._model,
            "messages": messages,
            "temperature": temperature,
        }
        data = await self._post("/chat/completions", payload)
        content = data["choices"][0]["message"]["content"]
        return ChatResponse(content=content, usage=data.get("usage", {}))

    async def embed(self, text: str, *, model: str | None = None) -> list[float]:
        payload = {"model": model or self._model, "input": text}
        data = await self._post("/embeddings", payload)
        return data["data"][0]["embedding"]

    async def _post(self, path: str, payload: dict) -> dict:
        headers = {"Authorization": f"Bearer {self._key}"} if self._key else {}
        delay = 1.0
        async with httpx.AsyncClient(
            base_url=self._base,
            timeout=self._timeout,
            headers=headers,
            transport=self._transport,
        ) as client:
            for attempt in range(self._max_retries):
                try:
                    resp = await client.post(path, json=payload)
                except httpx.TransportError as e:
                    if attempt == self._max_retries - 1:
                        raise ProviderError(f"network error: {e}") from e
                    await self._sleep(delay)
                    delay *= 2
                    continue
                if resp.status_code == 429 or resp.status_code >= 500:
                    if attempt == self._max_retries - 1:
                        raise ProviderError(f"{resp.status_code}: {resp.text[:200]}")
                    retry_after = resp.headers.get("Retry-After")
                    wait = delay
                    if retry_after:
                        try:
                            wait = float(retry_after)
                        except ValueError:
                            pass  # HTTP-date 形式：退回指数退避
                    await self._sleep(wait)
                    delay *= 2
                    continue
                if resp.status_code >= 400:
                    raise ProviderError(f"{resp.status_code}: {resp.text[:200]}")
                try:
                    return resp.json()
                except json.JSONDecodeError:
                    raise ProviderError(
                        f"non-JSON response (HTTP {resp.status_code}): {resp.text[:200]!r}"
                    )
        raise ProviderError("unreachable: retry loop exhausted")
