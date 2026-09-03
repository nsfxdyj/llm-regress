# src/llm_regress/providers/fake.py
from __future__ import annotations

import hashlib

from .base import ChatResponse


class FakeLLMClient:
    """脚本化假客户端：按最后一条 user 消息内容映射响应。用于测试与 demo。"""

    def __init__(self, responses: dict[str, str] | None = None, default: str = "ok"):
        self._responses = responses or {}
        self._default = default
        self.calls: list[dict] = []

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
    ) -> ChatResponse:
        self.calls.append({"messages": messages, "model": model, "temperature": temperature})
        key = messages[-1]["content"]
        content = self._responses.get(key, self._default)
        return ChatResponse(content=content, usage={"total_tokens": max(1, len(content) // 4)})

    async def embed(self, text: str, *, model: str | None = None) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [b / 255.0 for b in digest[:16]]
