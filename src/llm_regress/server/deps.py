from __future__ import annotations

from fastapi import Request

from ..models import TestSuite
from ..providers.base import LLMClient
from ..providers.openai_compat import OpenAICompatClient
from .db import Database


def get_db(request: Request) -> Database:
    return request.app.state.db


def make_clients(suite: TestSuite) -> tuple[LLMClient, LLMClient]:
    """默认客户端工厂：与 CLI 的 _make_clients 行为一致。测试通过 create_app(client_factory=...) 替换。"""
    target = OpenAICompatClient(suite.target)
    judge = OpenAICompatClient(suite.judge) if suite.judge else target
    return target, judge
