# src/llm_regress/providers/base.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class ProviderError(Exception):
    """LLM 端点调用失败（含 HTTP 错误与网络错误）。"""


@dataclass
class ChatResponse:
    content: str
    usage: dict = field(default_factory=dict)


class LLMClient(Protocol):
    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
    ) -> ChatResponse: ...

    async def embed(self, text: str, *, model: str | None = None) -> list[float]: ...
