# tests/test_factory.py
import pytest

from llm_regress.evaluators.factory import EvaluatorConfigError, build_evaluators, validate_suite
from llm_regress.models import EvaluatorConfig, TestSuite
from llm_regress.providers.fake import FakeLLMClient

CLIENT = FakeLLMClient()


def make_suite(evaluators):
    return TestSuite.model_validate(
        {
            "name": "s",
            "target": {"base_url": "http://x", "model": "m"},
            "cases": [{"id": "c1", "input": "q", "evaluators": evaluators}],
        }
    )


def test_builds_rule_and_weight():
    built = build_evaluators(
        [EvaluatorConfig(type="contains", weight=2.0, params={"keywords": ["a"]})],
        target_client=CLIENT,
        judge_client=CLIENT,
    )
    ev, weight = built[0]
    assert ev.name == "contains" and weight == 2.0


def test_unknown_type_raises():
    with pytest.raises(EvaluatorConfigError, match="unknown evaluator type"):
        build_evaluators(
            [EvaluatorConfig(type="magic")],
            target_client=CLIENT,
            judge_client=CLIENT,
        )


def test_bad_params_raise_config_error_not_value_error():
    with pytest.raises(EvaluatorConfigError, match="contains"):
        build_evaluators(
            [EvaluatorConfig(type="contains", params={})],
            target_client=CLIENT,
            judge_client=CLIENT,
        )


def test_invalid_regex_pattern_is_config_error():
    with pytest.raises(EvaluatorConfigError, match="regex"):
        build_evaluators(
            [EvaluatorConfig(type="regex", params={"pattern": "([unclosed"})],
            target_client=CLIENT,
            judge_client=CLIENT,
        )
    suite = make_suite([{"type": "regex", "params": {"pattern": "([unclosed"}}])
    with pytest.raises(EvaluatorConfigError, match="regex"):
        validate_suite(suite, target_client=CLIENT, judge_client=CLIENT)


def test_validate_suite_fails_fast_before_any_api_call():
    suite = make_suite([{"type": "contains", "params": {}}])
    with pytest.raises(EvaluatorConfigError):
        validate_suite(suite, target_client=CLIENT, judge_client=CLIENT)
    assert CLIENT.calls == []  # 没有发生任何 LLM 调用


def test_validate_suite_ok():
    suite = make_suite([{"type": "judge", "params": {"mode": "absolute"}}])
    validate_suite(suite, target_client=CLIENT, judge_client=CLIENT)
