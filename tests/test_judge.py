# tests/test_judge.py
import pytest

from llm_regress.evaluators.judge import JudgeEvaluator
from llm_regress.models import TestCase
from llm_regress.providers.fake import FakeLLMClient

CASE = TestCase(id="c", input="任务内容", expected="参考答案")


def judge_client(payload: str) -> FakeLLMClient:
    return FakeLLMClient(default=payload)


async def test_absolute_mode_scores_mean_over_five():
    ev = JudgeEvaluator(judge_client('{"accuracy": 5, "completeness": 3, "tone": 4, "reason": "尚可"}'), {})
    r = await ev.evaluate(CASE, "被测输出")
    assert abs(r.score - 0.8) < 1e-9
    assert r.raw is not None and "accuracy" in r.raw
    assert "尚可" in r.detail


async def test_judge_call_uses_temperature_zero():
    client = judge_client('{"accuracy": 1, "completeness": 1, "tone": 1, "reason": "差"}')
    await JudgeEvaluator(client, {}).evaluate(CASE, "x")
    assert client.calls[0]["temperature"] == 0.0


async def test_absolute_mode_tolerates_markdown_fence():
    ev = JudgeEvaluator(judge_client('```json\n{"accuracy": 4, "completeness": 4, "tone": 4, "reason": "好"}\n```'), {})
    r = await ev.evaluate(CASE, "被测输出")
    assert abs(r.score - 0.8) < 1e-9


async def test_pairwise_worse_scores_zero():
    ev = JudgeEvaluator(judge_client('{"verdict": "worse", "reason": "遗漏要点"}'), {"mode": "pairwise"})
    r = await ev.evaluate(CASE, "被测输出")
    assert r.score == 0.0 and not r.passed


async def test_pairwise_requires_expected():
    case = TestCase(id="c", input="任务内容")
    ev = JudgeEvaluator(judge_client('{"verdict": "tie", "reason": ""}'), {"mode": "pairwise"})
    r = await ev.evaluate(case, "被测输出")
    assert not r.passed and "expected" in r.detail


async def test_unparseable_judge_output_fails_closed():
    ev = JudgeEvaluator(judge_client("这不是 JSON"), {})
    r = await ev.evaluate(CASE, "被测输出")
    assert not r.passed and r.score == 0.0
    assert "unparseable" in r.detail
