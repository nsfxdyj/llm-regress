# tests/test_runner.py
import asyncio

from llm_regress.models import CaseStatus, TestSuite
from llm_regress.providers.base import ChatResponse
from llm_regress.providers.fake import FakeLLMClient
from llm_regress.runner import Runner, fingerprint


def suite_with(cases):
    return TestSuite.model_validate(
        {"name": "s", "target": {"base_url": "http://x", "model": "m"}, "cases": cases}
    )


def test_fingerprint_stable_and_sensitive():
    from llm_regress.models import TargetConfig

    a = fingerprint(TargetConfig(base_url="http://x", model="m"))
    assert a == fingerprint(TargetConfig(base_url="http://x", model="m"))
    assert a != fingerprint(TargetConfig(base_url="http://x", model="m2"))
    assert len(a) == 12


async def test_run_scores_and_passes():
    suite = suite_with(
        [{"id": "c1", "input": "问", "evaluators": [{"type": "contains", "params": {"keywords": ["猫"]}}]}]
    )
    runner = Runner(FakeLLMClient(default="这是猫"), FakeLLMClient())
    result = await runner.run(suite)
    r = result.results[0]
    assert r.status == CaseStatus.OK and r.passed and r.score == 1.0
    assert r.output == "这是猫"
    assert r.usage["total_tokens"] > 0


async def test_failing_case_does_not_kill_run():
    class BoomClient(FakeLLMClient):
        async def complete(self, messages, *, model=None, temperature=0.0):
            if messages[-1]["content"] == "炸":
                raise RuntimeError("boom")
            return await super().complete(messages, model=model, temperature=temperature)

    suite = suite_with([{"id": "bad", "input": "炸"}, {"id": "good", "input": "正常"}])
    result = await Runner(BoomClient(), FakeLLMClient()).run(suite)
    by_id = {r.case_id: r for r in result.results}
    assert by_id["bad"].status == CaseStatus.ERROR and "boom" in by_id["bad"].error
    assert by_id["good"].status == CaseStatus.OK


async def test_case_timeout_marks_error():
    class SlowClient(FakeLLMClient):
        async def complete(self, messages, *, model=None, temperature=0.0):
            await asyncio.sleep(5)
            return ChatResponse(content="too late")

    suite = suite_with([{"id": "slow", "input": "q"}])
    result = await Runner(SlowClient(), FakeLLMClient(), case_timeout=0.05).run(suite)
    assert result.results[0].status == CaseStatus.ERROR
    assert "timed out" in result.results[0].error


async def test_evaluator_hang_marks_case_error():
    class HungEmbedClient(FakeLLMClient):
        async def embed(self, text, *, model=None):
            await asyncio.sleep(5)
            return [0.0]

    # target 正常返回，但 similarity 评测器里的 embed 挂住：整个用例应超时报错
    suite = suite_with(
        [{"id": "c", "input": "q", "expected": "ref",
          "evaluators": [{"type": "similarity"}]}]
    )
    result = await Runner(HungEmbedClient(), FakeLLMClient(), case_timeout=0.05).run(suite)
    r = result.results[0]
    assert r.status == CaseStatus.ERROR
    assert "timed out" in r.error


def test_concurrency_zero_rejected():
    import pytest

    with pytest.raises(ValueError, match="concurrency"):
        Runner(FakeLLMClient(), concurrency=0)
    with pytest.raises(ValueError, match="concurrency"):
        Runner(FakeLLMClient(), concurrency=-2)


async def test_evaluator_exception_becomes_zero_score_not_case_error():
    class BadEmbedClient(FakeLLMClient):
        async def embed(self, text, *, model=None):
            raise RuntimeError("embed down")

    suite = suite_with(
        [{"id": "c", "input": "q", "expected": "ref",
          "evaluators": [{"type": "similarity"}, {"type": "contains", "params": {"keywords": ["ok"]}}]}]
    )
    # target 正常、embed 挂掉：similarity 记 0 分，contains 正常评
    runner = Runner(BadEmbedClient(default="ok"), FakeLLMClient())
    result = await runner.run(suite)
    r = result.results[0]
    assert r.status == CaseStatus.OK  # 用例本身不报错
    sim = next(e for e in r.evals if e.evaluator == "similarity")
    assert sim.score == 0.0 and "evaluator error" in sim.detail
    assert any(e.evaluator == "contains" and e.passed for e in r.evals)


async def test_zero_total_weight_does_not_kill_siblings():
    suite = suite_with([
        {"id": "zerow", "input": "q",
         "evaluators": [{"type": "contains", "params": {"keywords": ["x"]}, "weight": 0.0},
                        {"type": "contains", "params": {"keywords": ["y"]}, "weight": 0.0}]},
        {"id": "normal", "input": "q",
         "evaluators": [{"type": "contains", "params": {"keywords": ["ok"]}}]},
    ])
    result = await Runner(FakeLLMClient(default="ok"), FakeLLMClient()).run(suite)
    by_id = {r.case_id: r for r in result.results}
    assert by_id["zerow"].status == CaseStatus.OK and by_id["zerow"].score == 1.0
    assert by_id["normal"].status == CaseStatus.OK and by_id["normal"].passed


async def test_concurrency_limit_respected():
    in_flight = 0
    peak = 0

    class TrackClient(FakeLLMClient):
        async def complete(self, messages, *, model=None, temperature=0.0):
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1
            return await super().complete(messages, model=model, temperature=temperature)

    suite = suite_with([{"id": f"c{i}", "input": f"q{i}"} for i in range(8)])
    await Runner(TrackClient(), FakeLLMClient(), concurrency=2).run(suite)
    assert peak <= 2
