# src/llm_regress/evaluators/similarity.py
from __future__ import annotations

import math

from ..models import EvalResult, TestCase
from ..providers.base import LLMClient


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("embedding dimension mismatch")
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class SimilarityEvaluator:
    name = "similarity"

    def __init__(self, client: LLMClient, params: dict):
        self._client = client
        self._threshold = float(params.get("threshold", 0.85))
        self._model = params.get("model")

    async def evaluate(self, case: TestCase, output: str) -> EvalResult:
        if case.expected is None:
            return EvalResult(
                evaluator=self.name,
                score=0.0,
                passed=False,
                detail="similarity requires case.expected as reference",
            )
        ea = await self._client.embed(case.expected, model=self._model)
        eb = await self._client.embed(output, model=self._model)
        sim = cosine(ea, eb)
        return EvalResult(
            evaluator=self.name,
            score=sim,
            passed=sim >= self._threshold,
            detail=f"cosine={sim:.3f}, threshold={self._threshold}",
        )
