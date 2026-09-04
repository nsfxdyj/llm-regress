# tests/test_ci_e2e.py
"""端到端 CI 流程：baseline → 篡改 → run（四种 format 同开）→ comment。

整条链路只走 CLI 表面（typer CliRunner），通过 monkeypatch ``_make_clients``
注入 FakeLLMClient，无任何真实网络 / 真实 LLM 调用。各测试函数共享一个
module 级 scenario fixture（整个流程只跑一遍），分别对四种渲染产物与
comment 正文做真实行为断言。
"""
import re
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from llm_regress import cli
from llm_regress.github_api import COMMENT_MARKER
from llm_regress.providers.fake import FakeLLMClient

runner = CliRunner()

SUITE = """
name: e2e-demo
target:
  base_url: https://api.deepseek.com
  model: deepseek-chat
cases:
  - id: c-ok
    input: 问好
    evaluators:
      - type: contains
        params: {keywords: ["你好"]}
  - id: c-reg
    input: 问猫
    expected: 这是猫
    evaluators:
      - type: contains
        params: {keywords: ["猫"]}
"""

# 篡改后的回答故意带 XSS 载荷，端到端验证 HTML 转义
TAMPERED_ANSWER = "这是狗<script>alert(1)</script>"


@pytest.fixture(scope="module")
def scenario(tmp_path_factory):
    """完整跑一遍 CI 流程，返回所有产物供各测试函数断言。"""
    root = tmp_path_factory.mktemp("ci-e2e")
    mp = pytest.MonkeyPatch()
    mp.chdir(root)

    state = {"answers": {"问好": "你好世界", "问猫": "这是猫"}}

    def _make(suite):
        return (
            FakeLLMClient(responses=dict(state["answers"])),
            FakeLLMClient(default="{}"),
        )

    mp.setattr(cli, "_make_clients", _make)
    suite = root / "suite.yaml"
    suite.write_text(SUITE, encoding="utf-8")

    baseline_result = runner.invoke(cli.app, ["baseline", str(suite)])

    state["answers"]["问猫"] = TAMPERED_ANSWER

    xml_path = root / "report.xml"
    html_path = root / "report.html"
    summary_file = root / "step_summary.md"
    summary_file.write_text("# CI 已有内容\n", encoding="utf-8")
    mp.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

    run_result = runner.invoke(
        cli.app,
        [
            "run", str(suite),
            "--format", "console",
            "--format", "junit",
            "--format", "github",
            "--format", "html",
            "--output", str(xml_path),
            "--output", str(html_path),
        ],
    )
    yield SimpleNamespace(
        root=root,
        suite=suite,
        baseline_result=baseline_result,
        run_result=run_result,
        xml_path=xml_path,
        html_path=html_path,
        summary_file=summary_file,
    )
    mp.undo()


def latest_run_file(scenario):
    """基线与回归 run 共用同一秒级时间戳时后者覆盖前者；取最新即篡改后的 run。"""
    runs = sorted((scenario.root / ".llm-regress" / "runs").glob("*.json"))
    assert runs, "run 命令应落盘至少一份 run JSON"
    return runs[-1]


# --- 流程主干：baseline 通过 → 篡改后 run 退出码 1，console 照常打印 ---

def test_baseline_then_tampered_run_exit_codes(scenario):
    assert scenario.baseline_result.exit_code == 0, scenario.baseline_result.output
    result = scenario.run_result
    assert result.exit_code == 1, result.output  # 回归 → 退出码 1
    # console 永远照常打印（即使还开了别的 format）
    assert "Suite: e2e-demo" in result.output
    assert "✓ c-ok" in result.output
    assert "✗ c-reg" in result.output
    assert "REGRESSION (baseline 1.00)" in result.output
    assert "Summary: regression: 1, unchanged: 1" in result.output


# --- JUnit XML：文件生成、可解析、回归标记正确 ---

def test_junit_report_parses_and_marks_regression(scenario):
    assert scenario.xml_path.exists()
    xml_text = scenario.xml_path.read_text(encoding="utf-8")
    assert xml_text.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    root = ET.fromstring(xml_text)
    assert root.get("name") == "e2e-demo"
    assert root.get("tests") == "2"
    assert root.get("failures") == "1"
    assert root.get("errors") == "0"

    cases = {c.get("name"): c for c in root.findall("testcase")}
    assert set(cases) == {"c-ok", "c-reg"}
    assert len(cases["c-ok"]) == 0  # 通过 → 空 testcase
    failure = cases["c-reg"].find("failure")
    assert failure is not None
    assert failure.get("message") == "score 0.00 below baseline 1.00"
    assert "[contains]" in failure.text  # 失败 evaluator 明细


# --- HTML：文件生成、XSS 转义、回归卡片标记 ---

def test_html_report_exists_escapes_and_marks_regression(scenario):
    assert scenario.html_path.exists()
    html = scenario.html_path.read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>")
    assert "e2e-demo" in html

    # XSS：模型输出里的 <script> 必须被转义，原文一律不得出现
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert" not in html

    # 回归卡片：徽标 + 基线 → 新分数 + 期望输出
    reg_card = html[html.index("c-reg"):]
    reg_card = reg_card[: reg_card.index("</section>")]
    assert "回归" in reg_card
    assert "1.00 → 0.00" in reg_card
    assert "这是猫" in reg_card  # expected 字段


# --- GitHub 注解：stdout 含 ::error 行，且在 console 输出之后 ---

def test_github_annotations_in_stdout(scenario):
    out = scenario.run_result.output
    annotation = "::error title=llm-regress regression::c-reg 1.00 -> 0.00"
    assert annotation in out
    assert "regression::c-ok" not in out  # 未回归用例不出注解
    assert "::error title=llm-regress::" not in out  # 无普通失败行
    # 注解追加在 console 输出之后
    assert out.index("Summary:") < out.index("::error")


# --- GITHUB_STEP_SUMMARY：append markdown 摘要（含回归表格） ---

def test_step_summary_file_received_markdown(scenario):
    body = scenario.summary_file.read_text(encoding="utf-8")
    assert body.startswith("# CI 已有内容\n")  # append 而非覆盖
    assert "## llm-regress 报告" in body
    assert "> ❌ 检测到 1 个回归" in body
    assert "| c-reg | ❌ 失败 | 0.00 | 1.00 | 回归 |" in body
    assert "| c-ok | ✅ 通过 | 1.00 | 1.00 | 不变 |" in body
    assert "Summary: regression: 1, unchanged: 1" in body


# --- comment 子命令：mock HTTP，正文含同一份回归表格 ---

def test_comment_posts_regression_table(scenario, monkeypatch, tmp_path):
    monkeypatch.chdir(scenario.root)  # comment 从 cwd 重新加载基线计算对比
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    calls = []

    class Transport:
        """替换 GitHubAPI._request 的可调用对象（不做描述符绑定），零网络。"""

        def __call__(self, method, path, body=None):
            calls.append((method, path, body))
            if method == "GET":
                return []  # 无旧评论 → 应走 POST
            return {"html_url": "https://github.com/o/n/issues/7#issuecomment-1"}

    monkeypatch.setattr("llm_regress.github_api.GitHubAPI._request", Transport())
    result = runner.invoke(
        cli.app,
        [
            "comment",
            "--repo", "o/n",
            "--pr", "7",
            "--run-file", str(latest_run_file(scenario)),
        ],
    )
    assert result.exit_code == 0, result.output
    assert [m for m, _, _ in calls] == ["GET", "POST"]
    _, path, body = calls[-1]
    assert path == "/repos/o/n/issues/7/comments"
    text = body["body"]
    # 与 step summary 同源的回归表格 + 幂等标记
    assert "## llm-regress 报告" in text
    assert "> ❌ 检测到 1 个回归" in text
    assert "| c-reg | ❌ 失败 | 0.00 | 1.00 | 回归 |" in text
    assert COMMENT_MARKER in text
    assert "https://github.com/o/n/issues/7#issuecomment-1" in result.output


# --- 一致性扫荡：四种渲染对同一份 run/comparison 不得互相矛盾 ---

def test_renderers_agree_on_same_run(scenario):
    xml_root = ET.fromstring(scenario.xml_path.read_text(encoding="utf-8"))
    html = scenario.html_path.read_text(encoding="utf-8")
    md = scenario.summary_file.read_text(encoding="utf-8")
    out = scenario.run_result.output

    # 回归数：markdown 警告行 == junit failures == HTML 摘要条 == 注解行数
    alert_n = int(re.search(r"检测到 (\d+) 个回归", md).group(1))
    junit_failures = int(xml_root.get("failures"))
    html_reg = int(
        re.search(r'<div class="stat reg"><div class="num">(\d+)</div>', html).group(1)
    )
    annotation_regs = out.count("::error title=llm-regress regression::")
    assert alert_n == junit_failures == html_reg == annotation_regs == 1

    # 总数：junit tests == HTML 摘要条总计 == markdown 表格数据行数
    junit_tests = int(xml_root.get("tests"))
    html_total = int(
        re.search(
            r'<div class="stat"><div class="num">(\d+)</div><div class="label">总计</div>',
            html,
        ).group(1)
    )
    md_rows = len(re.findall(r"^\| c-", md, flags=re.M))
    assert junit_tests == html_total == md_rows == 2

    # Summary 行：console 与 markdown 摘要逐字一致（同源 comparison.summary()）
    console_summary = next(
        line for line in out.splitlines() if line.startswith("Summary:")
    )
    md_summary = next(
        line for line in md.splitlines() if line.startswith("Summary:")
    )
    assert console_summary == md_summary == "Summary: regression: 1, unchanged: 1"


def test_error_case_counts_agree_across_renderers():
    """补充 e2e 未覆盖的用例：error / 普通失败在四种渲染里的计数语义一致。

    约定（被本测试钉死）：junit failures = 非 error 的失败数（回归 + 普通失败）；
    markdown 的 ❌ 警告行只数 regression；github 注解 = 回归行 + 普通失败行 + 错误行。
    """
    import html as _html_mod

    from llm_regress.baseline import CaseDelta, Comparison
    from llm_regress.ci_report import (
        render_github_annotations,
        render_html,
        render_junit,
        render_markdown_summary,
    )
    from llm_regress.models import CaseResult, CaseStatus, RunResult

    run = RunResult(
        suite_name="x",
        target_fingerprint="t",
        judge_fingerprint="j",
        started_at="2026-09-04T00:00:00",
        results=[
            CaseResult(case_id="ok", score=1.0, passed=True),
            CaseResult(case_id="reg", score=0.2, passed=False),
            CaseResult(case_id="fail", score=0.5, passed=False),
            CaseResult(case_id="boom", status=CaseStatus.ERROR, error="api down"),
        ],
    )
    comparison = Comparison(
        deltas=[
            CaseDelta("ok", 1.0, 1.0, "unchanged"),
            CaseDelta("reg", 0.9, 0.2, "regression"),
            CaseDelta("fail", 0.5, 0.5, "unchanged"),
            CaseDelta("boom", 0.8, None, "error"),
        ]
    )

    xml_root = ET.fromstring(render_junit(run, comparison))
    html = render_html(run, comparison)
    md = render_markdown_summary(run, comparison)
    annotations = render_github_annotations(run, comparison).splitlines()

    def html_stat(cls, label):
        m = re.search(
            rf'<div class="stat{cls}"><div class="num">(\d+)</div>'
            rf'<div class="label">{label}</div>',
            html,
        )
        return int(m.group(1))

    # error 计数：junit errors == HTML 错误 == markdown 错误行 == error 注解
    err_annotations = sum("llm-regress error::" in a for a in annotations)
    assert int(xml_root.get("errors")) == html_stat(" err", "错误")
    assert int(xml_root.get("errors")) == md.count("⚠️ 错误") == err_annotations == 1

    # 失败计数：junit failures = 回归 + 普通失败 = 两类失败注解之和
    fail_annotations = sum(
        a.startswith("::error") and "error::" not in a for a in annotations
    )
    assert int(xml_root.get("failures")) == fail_annotations == 2
    assert html_stat(" reg", "回归") == 1  # HTML 摘要条只数回归
    assert "检测到 1 个回归" in md

    # 通过计数：junit 空 testcase == HTML 通过 == markdown ✅ 行
    empty_cases = sum(len(c) == 0 for c in xml_root.findall("testcase"))
    assert empty_cases == html_stat(" ok", "通过") == md.count("✅ 通过") == 1

    # 每个用例在四种渲染里都恰好出现一次（removed 不进任何渲染）
    md_rows = md.count("✅ 通过") + md.count("❌ 失败") + md.count("⚠️ 错误")
    assert len(xml_root.findall("testcase")) == md_rows
    assert html.count('<section class="card') == 4
    assert _html_mod.escape("boom") in html  # error 用例也有卡片
