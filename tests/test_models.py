from llm_regress.models import (
    CaseResult,
    CaseStatus,
    EvalResult,
    RunResult,
    TestSuite,
)


def test_suite_validates_from_dict():
    suite = TestSuite.model_validate(
        {
            "name": "demo",
            "target": {"base_url": "https://api.deepseek.com", "model": "deepseek-chat"},
            "cases": [{"id": "c1", "input": "你好"}],
        }
    )
    assert suite.target.provider == "openai-compatible"
    assert suite.cases[0].pass_threshold == 0.8
    assert suite.judge is None


def test_case_result_defaults():
    r = CaseResult(case_id="c1", status=CaseStatus.OK)
    assert r.output == ""
    assert r.evals == []
    assert r.passed is False
    assert r.error is None


def test_run_result_roundtrip_json():
    run = RunResult(
        suite_name="demo",
        target_fingerprint="abc123",
        judge_fingerprint=None,
        started_at="2026-09-03T00:00:00+00:00",
        results=[
            CaseResult(
                case_id="c1",
                status=CaseStatus.OK,
                output="hi",
                evals=[EvalResult(evaluator="contains", score=1.0, passed=True)],
                score=1.0,
                passed=True,
            )
        ],
    )
    restored = RunResult.model_validate_json(run.model_dump_json())
    assert restored.results[0].evals[0].evaluator == "contains"
