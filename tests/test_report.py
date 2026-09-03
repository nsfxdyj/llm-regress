from llm_regress.baseline import CaseDelta, Comparison
from llm_regress.models import CaseResult, CaseStatus, EvalResult, RunResult
from llm_regress.report import render_console, write_run_json


def make_run():
    return RunResult(
        suite_name="s",
        target_fingerprint="t",
        judge_fingerprint=None,
        started_at="2026-09-03T12:00:00+00:00",
        results=[
            CaseResult(
                case_id="good", status=CaseStatus.OK, output="o",
                evals=[EvalResult(evaluator="contains", score=1.0, passed=True)],
                score=1.0, passed=True,
            ),
            CaseResult(case_id="bad", status=CaseStatus.OK, score=0.3, passed=False),
            CaseResult(case_id="err", status=CaseStatus.ERROR, error="boom"),
        ],
    )


def test_write_run_json(tmp_path):
    path = write_run_json(make_run(), tmp_path)
    assert path.parent.name == "runs"
    assert path.read_text(encoding="utf-8")


def test_render_console_marks_regressions():
    run = make_run()
    comp = Comparison(deltas=[
        CaseDelta("good", 1.0, 1.0, "unchanged"),
        CaseDelta("bad", 0.9, 0.3, "regression"),
        CaseDelta("err", 0.8, None, "error"),
    ])
    text = render_console(run, comp)
    assert "REGRESSION" in text and "bad" in text
    assert "ERROR" in text and "err" in text
    assert "regression: 1" in text


def test_render_console_without_comparison():
    text = render_console(make_run())
    assert "good" in text and "bad" in text
    assert "REGRESSION" not in text
