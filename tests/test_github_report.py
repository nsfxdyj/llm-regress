# tests/test_github_report.py
import pytest
from typer.testing import CliRunner

from llm_regress import cli
from llm_regress.baseline import CaseDelta, Comparison
from llm_regress.ci_report import render_github_annotations, render_markdown_summary
from llm_regress.models import CaseResult, CaseStatus, RunResult
from llm_regress.providers.fake import FakeLLMClient

runner = CliRunner()

SUITE = """
name: demo
target:
  base_url: https://api.deepseek.com
  model: deepseek-chat
cases:
  - id: c1
    input: 问
    evaluators:
      - type: contains
        params: {keywords: ["猫"]}
"""


@pytest.fixture
def fake_clients(monkeypatch):
    state = {"answer": "这是猫"}

    def _make(suite):
        return FakeLLMClient(default=state["answer"]), FakeLLMClient(default="{}")

    monkeypatch.setattr(cli, "_make_clients", _make)
    return state


def write_suite(tmp_path, text=SUITE):
    p = tmp_path / "suite.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def make_run(results, suite_name="demo", started_at="2026-09-04T00:00:00+00:00"):
    return RunResult(
        suite_name=suite_name,
        target_fingerprint="abc123",
        judge_fingerprint="abc123",
        started_at=started_at,
        results=results,
    )


# --- brief 验收 1：回归用例 → 注解行格式精确匹配（含分数箭头） ---

def test_regression_annotation_exact_format():
    run = make_run([CaseResult(case_id="c1", score=0.4, passed=False)])
    comparison = Comparison(deltas=[CaseDelta("c1", 0.9, 0.4, "regression")])
    assert (
        render_github_annotations(run, comparison)
        == "::error title=llm-regress regression::c1 0.90 -> 0.40"
    )


def test_plain_failure_and_error_annotation_formats():
    run = make_run(
        [
            CaseResult(case_id="c2", score=0.3, passed=False),
            CaseResult(case_id="boom", status=CaseStatus.ERROR, error="api down"),
            CaseResult(case_id="ok", score=1.0, passed=True),
        ]
    )
    assert render_github_annotations(run, None).splitlines() == [
        "::error title=llm-regress::c2 failed, score 0.30",
        "::error title=llm-regress error::boom api down",
    ]  # 通过用例不产生注解


# --- brief 验收 2：特殊字符转义（换行/% → %0A/%25，含 case_id 与 \r） ---

def test_annotation_escaping_percent_newline_carriage_return():
    run = make_run(
        [
            CaseResult(
                case_id="weird%\nname",
                status=CaseStatus.ERROR,
                error="boom\n100% bad\rend",
            )
        ]
    )
    assert (
        render_github_annotations(run, None)
        == "::error title=llm-regress error::weird%25%0Aname boom%0A100%25 bad%0Dend"
    )


# --- brief 验收 3：markdown 表格含 case_id、基线分数、变化列 ---

def test_markdown_table_has_case_baseline_and_change_columns():
    run = make_run(
        [
            CaseResult(case_id="c1", score=0.4, passed=False),
            CaseResult(case_id="c2", score=0.95, passed=True),
        ]
    )
    comparison = Comparison(
        deltas=[
            CaseDelta("c1", 0.9, 0.4, "regression"),
            CaseDelta("c2", 0.9, 0.95, "unchanged"),
            CaseDelta("gone", 0.8, None, "removed"),  # removed 不进表格
        ]
    )
    md = render_markdown_summary(run, comparison)
    assert md.startswith("## llm-regress 报告")
    assert "demo" in md and "2026-09-04T00:00:00+00:00" in md and "abc123" in md
    assert "| 用例 | 结果 | 分数 | 基线 | 变化 |" in md
    assert "| c1 | ❌ 失败 | 0.40 | 0.90 | 回归 |" in md
    assert "| c2 | ✅ 通过 | 0.95 | 0.90 | 不变 |" in md
    assert "gone" not in md
    assert "Summary: regression: 1, removed: 1, unchanged: 1" in md


# --- brief 验收 4：有回归时表格上方有 ❌ 提示行，无回归时没有 ---

def test_markdown_regression_alert_line_present_and_absent():
    run = make_run([CaseResult(case_id="c1", score=0.4, passed=False)])
    comparison = Comparison(deltas=[CaseDelta("c1", 0.9, 0.4, "regression")])
    md = render_markdown_summary(run, comparison)
    alert = "> ❌ 检测到 1 个回归"
    assert alert in md
    assert md.index(alert) < md.index("| 用例 |")  # 提示行在表格上方

    ok_run = make_run([CaseResult(case_id="c1", score=0.95, passed=True)])
    ok_comparison = Comparison(deltas=[CaseDelta("c1", 0.9, 0.95, "unchanged")])
    assert "❌ 检测到" not in render_markdown_summary(ok_run, ok_comparison)
    # 无对比时的 Summary 回退格式与 console 一致
    assert "Summary: 1/1 passed, 0 errors" in render_markdown_summary(ok_run, None)


# --- brief 验收 5：CLI --format github → stdout 含注解；GITHUB_STEP_SUMMARY 文件被 append ---

def test_cli_github_annotations_and_step_summary(tmp_path, fake_clients, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = write_suite(tmp_path)
    assert runner.invoke(cli.app, ["baseline", str(p)]).exit_code == 0
    fake_clients["answer"] = "完全不同且跑题的输出"
    summary_file = tmp_path / "summary.md"
    summary_file.write_text("# 已有内容\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

    result = runner.invoke(cli.app, ["run", str(p), "--format", "github"])
    assert result.exit_code == 1, result.output  # 回归退出码语义不变
    assert "Summary" in result.output  # console 仍照常打印
    assert (
        "::error title=llm-regress regression::c1 1.00 -> 0.00" in result.output
    )
    # 注解出现在 console 输出之后
    assert result.output.index("Summary") < result.output.index("::error")

    body = summary_file.read_text(encoding="utf-8")
    assert body.startswith("# 已有内容\n")  # append 而非覆盖
    assert "## llm-regress 报告" in body
    assert "> ❌ 检测到 1 个回归" in body
    assert "| c1 |" in body


# --- brief 验收 6：未设 GITHUB_STEP_SUMMARY 不报错（本地运行场景） ---

def test_cli_github_without_step_summary_env(tmp_path, fake_clients, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    p = write_suite(tmp_path)
    result = runner.invoke(cli.app, ["run", str(p), "--format", "github"])
    assert result.exit_code == 0, result.output
    assert "::error" not in result.output  # 全部通过 → 无注解


# --- 补充：github 不消费 --output；配对错误仍退出 3 ---

def test_github_format_does_not_consume_output(tmp_path, fake_clients, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = write_suite(tmp_path)
    result = runner.invoke(
        cli.app, ["run", str(p), "--format", "github", "--output", "x.md"]
    )
    assert result.exit_code == 3
    assert "--output" in result.output
