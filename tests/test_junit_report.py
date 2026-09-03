# tests/test_junit_report.py
import xml.etree.ElementTree as ET

import pytest
from typer.testing import CliRunner

from llm_regress import cli
from llm_regress.baseline import CaseDelta, Comparison
from llm_regress.ci_report import render_junit
from llm_regress.models import CaseResult, CaseStatus, EvalResult, RunResult
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


# --- brief 验收 1：全通过 → tests=2 failures=0 errors=0，可解析 ---

def test_all_pass_suite_attrs_and_parseable():
    run = make_run(
        [
            CaseResult(case_id="c1", score=1.0, passed=True),
            CaseResult(case_id="c2", score=0.9, passed=True),
        ]
    )
    xml = render_junit(run, None)
    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    root = ET.fromstring(xml)
    assert root.tag == "testsuite"
    assert root.get("name") == "demo"
    assert root.get("tests") == "2"
    assert root.get("failures") == "0"
    assert root.get("errors") == "0"
    assert root.get("timestamp") == "2026-09-04T00:00:00+00:00"
    cases = root.findall("testcase")
    assert [c.get("name") for c in cases] == ["c1", "c2"]
    assert all(c.get("classname") == "demo" for c in cases)
    assert all(len(c) == 0 for c in cases)  # 通过 → 空 testcase


# --- brief 验收 2：回归 → failure message 含基线分数，failures=1 ---

def test_regression_failure_message_has_baseline(tmp_path, fake_clients, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = write_suite(tmp_path)
    assert runner.invoke(cli.app, ["baseline", str(p)]).exit_code == 0
    fake_clients["answer"] = "完全不同且跑题的输出"
    out = tmp_path / "out.xml"
    result = runner.invoke(
        cli.app, ["run", str(p), "--format", "junit", "--output", str(out)]
    )
    assert result.exit_code == 1, result.output
    root = ET.fromstring(out.read_text(encoding="utf-8"))
    assert root.get("failures") == "1"
    failure = root.find("testcase/failure")
    assert failure is not None
    assert "score 0.00 below baseline 1.00" in failure.get("message")


# --- brief 验收 3：error 用例 → <error> 元素，errors=1 ---

def test_error_case_produces_error_element():
    run = make_run(
        [
            CaseResult(case_id="boom", status=CaseStatus.ERROR, error="api down"),
            CaseResult(case_id="ok", score=1.0, passed=True),
        ]
    )
    root = ET.fromstring(render_junit(run, None))
    assert root.get("errors") == "1"
    assert root.get("failures") == "0"
    err = root.find("testcase/error")
    assert err is not None
    assert err.get("message") == "api down"


# --- brief 验收 4：失败 evaluators 明细出现在 failure 文本里 ---

def test_failure_text_lists_failing_evaluators():
    run = make_run(
        [
            CaseResult(
                case_id="c1",
                score=0.0,
                passed=False,
                evals=[
                    EvalResult(
                        evaluator="contains", score=0.0, passed=False,
                        detail="missing keywords: 猫",
                    ),
                    EvalResult(
                        evaluator="length", score=1.0, passed=True,
                        detail="within limit",
                    ),
                ],
            )
        ]
    )
    root = ET.fromstring(render_junit(run, None))
    failure = root.find("testcase/failure")
    assert failure is not None
    assert "[contains] missing keywords: 猫" in failure.text
    assert "length" not in failure.text  # 只列失败的 evaluators


# --- brief 验收 5：CLI 集成，文件生成且 console 仍打印，退出码一致 ---

def test_cli_junit_output_and_console_still_printed(tmp_path, fake_clients, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = write_suite(tmp_path)
    out = tmp_path / "out.xml"
    plain = runner.invoke(cli.app, ["run", str(p)])
    result = runner.invoke(
        cli.app, ["run", str(p), "--format", "junit", "--output", str(out)]
    )
    assert result.exit_code == plain.exit_code  # 退出码与无 format 时一致
    assert "Summary" in result.output  # console 仍照常打印
    assert out.exists()
    root = ET.fromstring(out.read_text(encoding="utf-8"))
    assert root.get("tests") == "1"
    assert root.get("failures") == "0"


# --- brief 验收 6：junit 缺 --output → 退出 3 + stderr 提示 ---

def test_junit_without_output_exit_3(tmp_path, fake_clients, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = write_suite(tmp_path)
    result = runner.invoke(cli.app, ["run", str(p), "--format", "junit"])
    assert result.exit_code == 3
    assert "--output" in result.output


# --- 补充：无对比时的 failure message 格式 ---

def test_failure_message_without_comparison():
    run = make_run([CaseResult(case_id="c1", score=0.5, passed=False)])
    root = ET.fromstring(render_junit(run, None))
    failure = root.find("testcase/failure")
    assert failure is not None
    assert failure.get("message") == "failed, score 0.50"


# --- 补充：removed deltas 不进 XML，new 用例正常进 ---

def test_removed_deltas_excluded_and_new_cases_included():
    run = make_run([CaseResult(case_id="new-case", score=1.0, passed=True)])
    comparison = Comparison(
        deltas=[
            CaseDelta("new-case", None, 1.0, "new"),
            CaseDelta("gone-case", 0.9, None, "removed"),
        ]
    )
    root = ET.fromstring(render_junit(run, comparison))
    assert root.get("tests") == "1"
    assert [c.get("name") for c in root.findall("testcase")] == ["new-case"]


# --- 补充：未知 format → 退出 3 ---

def test_unknown_format_exit_3(tmp_path, fake_clients, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(cli.app, ["run", str(write_suite(tmp_path)), "--format", "bogus"])
    assert result.exit_code == 3
    assert "bogus" in result.output
