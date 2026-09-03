# tests/test_similarity.py
import math

from llm_regress.evaluators.similarity import SimilarityEvaluator, cosine
from llm_regress.models import TestCase
from llm_regress.providers.fake import FakeLLMClient


def test_cosine_basic():
    assert math.isclose(cosine([1, 0], [1, 0]), 1.0)
    assert math.isclose(cosine([1, 0], [0, 1]), 0.0)


async def test_identical_texts_pass():
    case = TestCase(id="c", input="q", expected="相同文本")
    ev = SimilarityEvaluator(FakeLLMClient(), {"threshold": 0.99})
    r = await ev.evaluate(case, "相同文本")
    assert r.passed and r.score > 0.99


async def test_different_texts_fail():
    case = TestCase(id="c", input="q", expected="预期答案甲")
    ev = SimilarityEvaluator(FakeLLMClient(), {"threshold": 0.99})
    r = await ev.evaluate(case, "完全不同的输出乙")
    assert not r.passed
    assert "cosine=" in r.detail


async def test_missing_expected_fails_closed():
    case = TestCase(id="c", input="q")  # no expected
    ev = SimilarityEvaluator(FakeLLMClient(), {})
    r = await ev.evaluate(case, "任意输出")
    assert not r.passed and "expected" in r.detail
