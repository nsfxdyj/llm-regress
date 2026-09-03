# tests/test_baseline.py
import pytest

from llm_regress.baseline import (
    JudgeChangedError,
    baseline_path,
    compare,
    load_baseline,
    save_baseline,
)
from llm_regress.models import CaseResult, CaseStatus, RunResult


def make_run(results, judge_fp="judge-x"):
    return RunResult(
        suite_name="s",
        target_fingerprint="t",
        judge_fingerprint=judge_fp,
        started_at="2026-09-03T00:00:00+00:00",
        results=results,
    )


def case(cid, score, passed=True, status=CaseStatus.OK):
    return CaseResult(case_id=cid, status=status, score=score, passed=passed)


def test_save_and_load_roundtrip(tmp_path):
    run = make_run([case("c1", 0.9)])
    path = save_baseline(run, tmp_path)
    assert path == baseline_path("s", tmp_path)
    loaded = load_baseline(path)
    assert loaded.results[0].score == 0.9


def test_score_drop_beyond_threshold_is_regression():
    baseline = make_run([case("c1", 0.9)])
    run = make_run([case("c1", 0.7)])
    comp = compare(run, baseline, regression_threshold=0.1)
    assert comp.has_regressions
    assert comp.deltas[0].change == "regression"


def test_small_drop_within_threshold_is_unchanged():
    comp = compare(make_run([case("c1", 0.85)]), make_run([case("c1", 0.9)]))
    assert not comp.has_regressions
    assert comp.deltas[0].change == "unchanged"


def test_pass_to_fail_is_regression_even_within_threshold():
    # pass_threshold 0.8：0.81 -> 0.79 分数降幅只有 0.02，但从过变不过
    comp = compare(make_run([case("c1", 0.79, passed=False)]), make_run([case("c1", 0.81)]))
    assert comp.has_regressions


def test_improvement_and_new_and_removed_cases():
    baseline = make_run([case("old", 0.5), case("gone", 0.9)])
    run = make_run([case("old", 0.9), case("fresh", 1.0)])
    comp = compare(run, baseline)
    changes = {d.case_id: d.change for d in comp.deltas}
    assert changes == {"old": "improved", "fresh": "new", "gone": "removed"}


def test_error_case_marked_error_not_regression():
    comp = compare(
        make_run([case("c1", 0.0, passed=False, status=CaseStatus.ERROR)]),
        make_run([case("c1", 0.9)]),
    )
    assert comp.deltas[0].change == "error"
    assert comp.has_errors and not comp.has_regressions


def test_judge_change_raises():
    with pytest.raises(JudgeChangedError) as exc:
        compare(make_run([case("c1", 0.9)], judge_fp="judge-new"), make_run([case("c1", 0.9)]))
    assert exc.value.old == "judge-x" and exc.value.new == "judge-new"


async def test_default_judge_fingerprint_follows_target():
    # 无 judge 段时裁判就是 target：仅换 target.model 必须改变 judge_fingerprint
    from llm_regress.models import TestSuite
    from llm_regress.providers.fake import FakeLLMClient
    from llm_regress.runner import Runner

    def suite(model):
        return TestSuite.model_validate(
            {"name": "s", "target": {"base_url": "http://x", "model": model},
             "cases": [{"id": "c1", "input": "q"}]}
        )

    run_a = await Runner(FakeLLMClient()).run(suite("m1"))
    run_b = await Runner(FakeLLMClient()).run(suite("m2"))
    assert run_a.judge_fingerprint is not None
    assert run_a.judge_fingerprint != run_b.judge_fingerprint
    with pytest.raises(JudgeChangedError):
        compare(run_b, run_a)
