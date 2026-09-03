from __future__ import annotations

from typing import Protocol

from ..models import EvalResult, TestCase


class Evaluator(Protocol):
    name: str

    async def evaluate(self, case: TestCase, output: str) -> EvalResult: ...
