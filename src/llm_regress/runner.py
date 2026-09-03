# src/llm_regress/runner.py
from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone

from .evaluators.factory import build_evaluators, validate_suite
from .models import (
    CaseResult,
    CaseStatus,
    EvalResult,
    RunResult,
    TargetConfig,
    TestCase,
    TestSuite,
)
from .providers.base import LLMClient


def fingerprint(config: TargetConfig) -> str:
    raw = f"{config.provider}|{config.base_url}|{config.model}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


class Runner:
    def __init__(
        self,
        target_client: LLMClient,
        judge_client: LLMClient | None = None,
        *,
        concurrency: int = 4,
        case_timeout: float = 120.0,
    ):
        if concurrency < 1:
            raise ValueError("concurrency must be >= 1")
        self._target = target_client
        self._judge = judge_client if judge_client is not None else target_client
        self._sem = asyncio.Semaphore(concurrency)
        self._case_timeout = case_timeout

    async def run(self, suite: TestSuite) -> RunResult:
        validate_suite(suite, target_client=self._target, judge_client=self._judge)
        results = await asyncio.gather(*(self._run_case(c) for c in suite.cases))
        return RunResult(
            suite_name=suite.name,
            target_fingerprint=fingerprint(suite.target),
            judge_fingerprint=fingerprint(suite.judge or suite.target),
            started_at=datetime.now(timezone.utc).isoformat(),
            results=list(results),
        )

    async def _run_case(self, case: TestCase) -> CaseResult:
        async with self._sem:
            try:
                return await asyncio.wait_for(
                    self._execute_case(case), timeout=self._case_timeout
                )
            except asyncio.TimeoutError:
                return CaseResult(
                    case_id=case.id, status=CaseStatus.ERROR,
                    input=case.input, expected=case.expected,
                    error=f"case timed out after {self._case_timeout}s",
                )

    async def _execute_case(self, case: TestCase) -> CaseResult:
        try:
            resp = await self._target.complete([{"role": "user", "content": case.input}])
        except Exception as e:
            return CaseResult(
                case_id=case.id, status=CaseStatus.ERROR,
                input=case.input, expected=case.expected, error=str(e),
            )

        evals: list[EvalResult] = []
        weighted: list[tuple[float, float]] = []
        for ev, weight in build_evaluators(
            case.evaluators, target_client=self._target, judge_client=self._judge
        ):
            try:
                r = await ev.evaluate(case, resp.content)
            except Exception as e:
                r = EvalResult(
                    evaluator=getattr(ev, "name", "unknown"),
                    score=0.0, passed=False, detail=f"evaluator error: {e}",
                )
            evals.append(r)
            weighted.append((r.score, weight))

        total_weight = sum(w for _, w in weighted)
        if weighted and total_weight > 0:
            score = sum(s * w for s, w in weighted) / total_weight
        else:
            score = 1.0  # 无评测器或总权重非正：调用成功即满分
        return CaseResult(
            case_id=case.id,
            status=CaseStatus.OK,
            input=case.input,
            expected=case.expected,
            output=resp.content,
            evals=evals,
            score=score,
            passed=score >= case.pass_threshold,
            usage=resp.usage,
        )
