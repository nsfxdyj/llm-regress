# tests/test_html_report.py
import pytest
from typer.testing import CliRunner

from llm_regress import cli
from llm_regress.baseline import CaseDelta, Comparison
from llm_regress.ci_report import render_html
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


# --- brief 验收 1：输出含 <!DOCTYPE html>、套件名、case_id ---

def test_doctype_suite_and_case_id_present():
    run = make_run([CaseResult(case_id="c1", score=1.0, passed=True)])
    html = render_html(run, None)
    assert html.startswith("<!DOCTYPE html>")
    assert '<html lang="zh-CN">' in html
    assert '<meta charset="utf-8">' in html
    assert "demo" in html
    assert "c1" in html
    assert "abc123" in html  # target 指纹
    assert "2026-09-04T00:00:00+00:00" in html


# --- brief 验收 2：回归用例卡片含回归标记与基线分数 ---

def test_regression_card_has_badge_and_baseline_score():
    run = make_run([CaseResult(case_id="c1", score=0.2, passed=False)])
    comparison = Comparison(deltas=[CaseDelta("c1", 0.9, 0.2, "regression")])
    html = render_html(run, comparison)
    assert ">回归</span>" in html
    assert "0.90 → 0.20" in html
    assert 'class="card s-reg"' in html
    # 摘要条回归计数为 1
    assert '<div class="stat reg"><div class="num">1</div>' in html


# --- brief 验收 3：XSS —— 转义后的出现，未转义的不出现 ---

def test_xss_payload_is_escaped():
    payload = "<script>alert(1)</script>"
    run = make_run(
        [
            CaseResult(
                case_id=payload,
                input=payload,
                expected=payload,
                output=payload,
                score=0.0,
                passed=False,
                evals=[
                    EvalResult(
                        evaluator="contains", score=0.0, passed=False,
                        detail=payload, raw=payload,
                    )
                ],
            ),
            CaseResult(
                case_id="err", status=CaseStatus.ERROR, error=payload,
            ),
        ]
    )
    html = render_html(run, None)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert" not in html
    # 整份文档不应出现任何未转义的 <script 标签
    assert "<script" not in html


# --- brief 验收 4：CLI --format html --output r.html 文件生成 ---

def test_cli_html_output_file_generated(tmp_path, fake_clients, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = write_suite(tmp_path)
    out = tmp_path / "r.html"
    plain = runner.invoke(cli.app, ["run", str(p)])
    result = runner.invoke(
        cli.app, ["run", str(p), "--format", "html", "--output", str(out)]
    )
    assert result.exit_code == plain.exit_code
    assert "Summary" in result.output  # console 仍照常打印
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>")
    assert "demo" in html
    assert "c1" in html


# --- brief 验收 5：judge raw 存在时在 <details> 内 ---

def test_judge_raw_inside_details():
    run = make_run(
        [
            CaseResult(
                case_id="c1", score=0.5, passed=False,
                evals=[
                    EvalResult(
                        evaluator="judge", score=0.5, passed=False,
                        detail="裁判评分偏低", raw='{"score": 0.5, "reason": "偏题"}',
                    )
                ],
            )
        ]
    )
    html = render_html(run, None)
    assert "<details>" in html
    assert "<summary>" in html
    assert "裁判原始输出" in html
    details_block = html.split("<details>", 1)[1]
    assert "偏题" in details_block


# --- 补充：error 用例卡片为黄色态且含错误信息 ---

def test_error_card_amber_with_error_message():
    run = make_run(
        [CaseResult(case_id="boom", status=CaseStatus.ERROR, error="api down")]
    )
    html = render_html(run, None)
    assert 'class="card s-err"' in html
    assert ">错误</span>" in html
    assert "api down" in html
    assert '<div class="stat err"><div class="num">1</div>' in html


# --- 补充：input/expected 快照渲染（runner 填充后），无则不渲染 ---

def test_input_and_expected_rendered_when_present():
    run = make_run(
        [
            CaseResult(
                case_id="c1", input="介绍一下猫", expected="猫是动物",
                output="猫很可爱", score=1.0, passed=True,
            ),
            CaseResult(case_id="c2", output="无快照", score=1.0, passed=True),
        ]
    )
    html = render_html(run, None)
    assert "介绍一下猫" in html
    assert "期望输出" in html
    assert "猫是动物" in html
    c2_card = html.split('case-id mono">c2<', 1)[1]
    assert "期望输出" not in c2_card.split("</section>", 1)[0]


# --- 补充：html 缺 --output → 退出 3 ---

def test_html_without_output_exit_3(tmp_path, fake_clients, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = write_suite(tmp_path)
    result = runner.invoke(cli.app, ["run", str(p), "--format", "html"])
    assert result.exit_code == 3
    assert "--output" in result.output
