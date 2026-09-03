# src/llm_regress/evaluators/judge.py
from __future__ import annotations

import json
import re

from ..models import EvalResult, TestCase
from ..providers.base import LLMClient


class JudgeParseError(Exception):
    """裁判输出无法解析。"""


ABSOLUTE_RUBRIC = """你是一个严格的输出质量评审。请根据评分标准给「模型回答」打分。

## 原始任务
{task}

## 参考期望（可能为空，仅供对照）
{expected}

## 模型回答
{answer}

## 评分标准（每项为 1-5 的整数）
- accuracy: 事实与指令的正确性
- completeness: 对任务要求的覆盖程度
- tone: 语气与格式是否符合任务语境

只输出 JSON，不要输出任何其他内容：
{{"accuracy": <int>, "completeness": <int>, "tone": <int>, "reason": "<一句话总评>"}}"""

PAIRWISE_RUBRIC = """你是一个严格的评审。比较「新回答」相对「基线回答」在完成原始任务上的质量。

## 原始任务
{task}

## 基线回答
{reference}

## 新回答
{answer}

只输出 JSON，不要输出任何其他内容：
{{"verdict": "better" | "tie" | "worse", "reason": "<一句话理由>"}}"""

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict:
    m = _JSON_RE.search(text)
    if not m:
        raise JudgeParseError(f"no JSON object in judge output: {text[:100]!r}")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise JudgeParseError(f"invalid JSON from judge: {e}") from e


class JudgeEvaluator:
    name = "judge"

    def __init__(self, client: LLMClient, params: dict):
        self._client = client
        self._mode = params.get("mode", "absolute")
        if self._mode not in ("absolute", "pairwise"):
            raise ValueError(f"judge mode must be 'absolute' or 'pairwise', got {self._mode!r}")
        self._model = params.get("model")

    async def evaluate(self, case: TestCase, output: str) -> EvalResult:
        if self._mode == "pairwise":
            return await self._pairwise(case, output)
        return await self._absolute(case, output)

    async def _ask(self, prompt: str) -> tuple[dict, str]:
        resp = await self._client.complete(
            [{"role": "user", "content": prompt}],
            model=self._model,
            temperature=0.0,
        )
        return _extract_json(resp.content), resp.content

    async def _absolute(self, case: TestCase, output: str) -> EvalResult:
        prompt = ABSOLUTE_RUBRIC.format(
            task=case.input, expected=case.expected or "（无）", answer=output
        )
        try:
            data, raw = await self._ask(prompt)
            scores = [int(data[k]) for k in ("accuracy", "completeness", "tone")]
        except (JudgeParseError, KeyError, TypeError, ValueError) as e:
            return EvalResult(
                evaluator=self.name, score=0.0, passed=False,
                detail=f"unparseable judge output: {e}",
            )
        score = (sum(scores) / 3) / 5
        return EvalResult(
            evaluator=self.name, score=score, passed=score >= 0.6,
            detail=str(data.get("reason", "")), raw=raw,
        )

    async def _pairwise(self, case: TestCase, output: str) -> EvalResult:
        if case.expected is None:
            return EvalResult(
                evaluator=self.name, score=0.0, passed=False,
                detail="pairwise judge requires case.expected as baseline reference",
            )
        prompt = PAIRWISE_RUBRIC.format(task=case.input, reference=case.expected, answer=output)
        try:
            data, raw = await self._ask(prompt)
            verdict = data["verdict"]
        except (JudgeParseError, KeyError, TypeError) as e:
            return EvalResult(
                evaluator=self.name, score=0.0, passed=False,
                detail=f"unparseable judge output: {e}",
            )
        score = {"better": 1.0, "tie": 0.5, "worse": 0.0}.get(verdict, 0.0)
        return EvalResult(
            evaluator=self.name, score=score, passed=verdict in ("better", "tie"),
            detail=f"verdict={verdict}: {data.get('reason', '')}", raw=raw,
        )
