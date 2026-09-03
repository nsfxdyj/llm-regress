# tests/test_rules.py
import pytest

from llm_regress.evaluators.rules import RULE_EVALUATORS
from llm_regress.models import TestCase

CASE = TestCase(id="c", input="irrelevant")


def make(t, params):
    return RULE_EVALUATORS[t](params)


async def test_contains_all_matched():
    r = await make("contains", {"keywords": ["猫", "可爱"]}).evaluate(CASE, "这只猫很可爱")
    assert r.passed and r.score == 1.0


async def test_contains_partial_missing():
    r = await make("contains", {"keywords": ["猫", "狗"]}).evaluate(CASE, "只有猫")
    assert not r.passed and r.score == 0.5
    assert "狗" in r.detail


async def test_not_contains():
    ok = await make("not_contains", {"keywords": ["违禁词"]}).evaluate(CASE, "正常内容")
    bad = await make("not_contains", {"keywords": ["违禁词"]}).evaluate(CASE, "含违禁词的内容")
    assert ok.passed and not bad.passed


async def test_json_valid():
    ok = await make("json_valid", {}).evaluate(CASE, '{"a": 1}')
    bad = await make("json_valid", {}).evaluate(CASE, "not json")
    assert ok.passed and not bad.passed and bad.score == 0.0


async def test_json_schema():
    ev = make(
        "json_schema",
        {"schema": {"type": "object", "required": ["name"]}},
    )
    ok = await ev.evaluate(CASE, '{"name": "x", "age": 3}')
    bad = await ev.evaluate(CASE, '{"age": 3}')
    assert ok.passed and not bad.passed


async def test_length():
    ev = make("length", {"min_chars": 3, "max_chars": 5})
    assert (await ev.evaluate(CASE, "abcd")).passed
    assert not (await ev.evaluate(CASE, "ab")).passed
    assert not (await ev.evaluate(CASE, "abcdef")).passed


async def test_regex_with_group_compare():
    ev = make("regex", {"pattern": r"价格[：:]\s*(\d+)", "expected": "42"})
    assert (await ev.evaluate(CASE, "价格：42 元")).passed
    assert not (await ev.evaluate(CASE, "价格：43 元")).passed


def test_params_validation():
    with pytest.raises(ValueError):
        make("contains", {})
    with pytest.raises(ValueError):
        make("length", {})
