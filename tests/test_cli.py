# tests/test_cli.py
import pytest
from typer.testing import CliRunner

from llm_regress import cli
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


def test_init_scaffolds_example(tmp_path):
    result = runner.invoke(cli.app, ["init", str(tmp_path / "new.yaml")])
    assert result.exit_code == 0
    assert "cases:" in (tmp_path / "new.yaml").read_text(encoding="utf-8")


def test_run_without_baseline_exit_0(tmp_path, fake_clients, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(cli.app, ["run", str(write_suite(tmp_path))])
    assert result.exit_code == 0, result.output
    assert "Summary" in result.output


def test_regression_exit_1(tmp_path, fake_clients, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = write_suite(tmp_path)
    assert runner.invoke(cli.app, ["baseline", str(p)]).exit_code == 0
    fake_clients["answer"] = "完全不同且跑题的输出"
    result = runner.invoke(cli.app, ["run", str(p)])
    assert result.exit_code == 1, result.output
    assert "REGRESSION" in result.output


def test_no_regression_after_baseline_exit_0(tmp_path, fake_clients, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = write_suite(tmp_path)
    runner.invoke(cli.app, ["baseline", str(p)])
    assert runner.invoke(cli.app, ["run", str(p)]).exit_code == 0


def test_judge_change_exit_3(tmp_path, fake_clients, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = write_suite(tmp_path)
    runner.invoke(cli.app, ["baseline", str(p)])
    # 换裁判：往 YAML 里加 judge 段
    p.write_text(SUITE.replace("cases:", "judge:\n  base_url: https://other.api\n  model: j2\ncases:"), encoding="utf-8")
    result = runner.invoke(cli.app, ["run", str(p)])
    assert result.exit_code == 3
    assert "Judge changed" in result.output


def test_case_error_exit_2(tmp_path, fake_clients, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def boom_make(suite):
        class Boom(FakeLLMClient):
            async def complete(self, messages, *, model=None, temperature=0.0):
                raise RuntimeError("api down")

        return Boom(), FakeLLMClient()

    monkeypatch.setattr(cli, "_make_clients", boom_make)
    result = runner.invoke(cli.app, ["run", str(write_suite(tmp_path))])
    assert result.exit_code == 2


def test_bad_config_exit_3(tmp_path, fake_clients, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(cli.app, ["run", str(tmp_path / "missing.yaml")])
    assert result.exit_code == 3


BAD_REGEX_SUITE = """
name: demo
target:
  base_url: https://api.deepseek.com
  model: deepseek-chat
cases:
  - id: c1
    input: 问
    evaluators:
      - type: regex
        params: {pattern: "([unclosed"}
"""


def test_invalid_regex_suite_exit_3(tmp_path, fake_clients, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(cli.app, ["run", str(write_suite(tmp_path, BAD_REGEX_SUITE))])
    assert result.exit_code == 3, result.output
    assert "Config error" in result.output
