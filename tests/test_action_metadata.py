# tests/test_action_metadata.py
"""Drift guard: action.yml / CI workflows / README stay consistent with cli.py.

防止文档漂移：
1. action.yml、.github/workflows/ci.yaml、examples/github-action.yaml 都能被
   yaml.safe_load 解析；
2. action.yml 具备 name/description/inputs/runs，且 suite-file 是 required
   input，runs.using 为 composite；
3. 本仓库 CI 含 backend（pytest）与 frontend（npm）两个 job；
4. README、示例 workflow、action.yml 中出现的每个 ``llm-regress`` CLI 选项
   都真实存在于 typer app 对应子命令的 --help 输出里（选项通过 CliRunner
   内省 cli.py 得到，不靠硬编码清单）。
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from typer.testing import CliRunner

from llm_regress.cli import app

ROOT = Path(__file__).resolve().parent.parent

ACTION_YML = ROOT / "action.yml"
CI_YAML = ROOT / ".github" / "workflows" / "ci.yaml"
EXAMPLE_YAML = ROOT / "examples" / "github-action.yaml"
README = ROOT / "README.md"

FLAG_RE = re.compile(r"--[a-z][a-z0-9-]*")
COMMAND_RE = re.compile(r"llm-regress\s+(run|baseline|comment|init)\b")
COMMANDS = ("run", "baseline", "comment", "init")


def _help_flags() -> dict[str, set[str]]:
    """Introspect the real typer app: subcommand -> set of --flags in --help."""
    # 固定终端宽度：CI runner 的终端宽度不确定（过窄时 rich 会省略选项面板，
    # 导致解析不到任何 flag），这里钉死为 120 列保证输出稳定。
    runner = CliRunner(env={"COLUMNS": "120"})
    flags: dict[str, set[str]] = {}
    for cmd in COMMANDS:
        result = runner.invoke(app, [cmd, "--help"])
        assert result.exit_code == 0, f"--help failed for {cmd}: {result.output}"
        flags[cmd] = set(FLAG_RE.findall(result.output))
    return flags


def _logical_lines(text: str) -> list[str]:
    """Join backslash continuations so multi-line CLI invocations stay whole."""
    return re.sub(r"\\\r?\n\s*", " ", text).splitlines()


def _document_flags(path: Path) -> list[tuple[str, str, str]]:
    """Extract (subcommand, flag, line) for every llm-regress invocation."""
    found: list[tuple[str, str, str]] = []
    for line in _logical_lines(path.read_text(encoding="utf-8")):
        m = COMMAND_RE.search(line)
        if not m:
            continue
        for flag in FLAG_RE.findall(line[m.end():]):
            found.append((m.group(1), flag, line.strip()))
    return found


def test_yaml_files_parse():
    for path in (ACTION_YML, CI_YAML, EXAMPLE_YAML):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict), f"{path.name} did not parse to a mapping"


def test_action_metadata_structure():
    action = yaml.safe_load(ACTION_YML.read_text(encoding="utf-8"))
    for key in ("name", "description", "inputs", "runs"):
        assert key in action, f"action.yml missing '{key}'"
    assert action["runs"]["using"] == "composite"
    inputs = action["inputs"]
    assert "suite-file" in inputs, "action.yml must declare the suite-file input"
    assert inputs["suite-file"].get("required") is True
    # 其余可选输入带默认值，与 README 的 action 用法对应
    for optional in ("python-version", "format", "output"):
        assert optional in inputs, f"action.yml missing optional input '{optional}'"
        assert inputs[optional].get("default"), f"input '{optional}' needs a default"


def test_repo_ci_workflow_structure():
    ci = yaml.safe_load(CI_YAML.read_text(encoding="utf-8"))
    assert "backend" in ci["jobs"] and "frontend" in ci["jobs"]
    backend_steps = "\n".join(
        s.get("run", "") for s in ci["jobs"]["backend"]["steps"]
    )
    assert "pytest" in backend_steps
    frontend_steps = "\n".join(
        s.get("run", "") for s in ci["jobs"]["frontend"]["steps"]
    )
    for cmd in ("npm ci", "npm test", "npm run build"):
        assert cmd in frontend_steps


def test_action_run_command_only_pairs_output_with_file_formats():
    """--output 只能与文件类 --format（junit/html）配对，否则 CLI 退出 3。

    github 格式不消费 --output；action 的 run 命令必须按 format 条件传入。
    """
    action = yaml.safe_load(ACTION_YML.read_text(encoding="utf-8"))
    run_blocks = [
        s["run"] for s in action["runs"]["steps"] if isinstance(s.get("run"), str)
    ]
    joined = "\n".join(run_blocks)
    assert "--format" in joined
    # 条件配对：只有 junit|html 分支才追加 --output
    assert re.search(r"junit\|html\).*--output", joined, re.S), (
        "action.yml must pass --output only for file-producing formats"
    )
    assert "--format console" in joined, "console output must stay on by default"


def test_cli_flags_in_docs_exist():
    """README / 示例 workflow 里出现的每个 llm-regress 选项都必须真实存在。"""
    help_flags = _help_flags()
    # 基本事实：run/baseline 支持 --format 与 --output；comment 的三件套在
    assert {"--format", "--output"} <= help_flags["run"]
    assert {"--format", "--output"} <= help_flags["baseline"]
    assert {"--repo", "--pr", "--run-file"} <= help_flags["comment"]

    for doc in (README, EXAMPLE_YAML):
        for subcommand, flag, line in _document_flags(doc):
            assert flag in help_flags[subcommand], (
                f"{doc.name}: flag '{flag}' not in 'llm-regress {subcommand}' "
                f"--help (line: {line})"
            )


def test_cli_flags_in_action_yml_exist():
    """action.yml 只调用 run 子命令；其中出现的选项必须在 run --help 里。"""
    help_flags = _help_flags()
    action = yaml.safe_load(ACTION_YML.read_text(encoding="utf-8"))
    for step in action["runs"]["steps"]:
        run_block = step.get("run")
        if not isinstance(run_block, str) or "llm-regress" not in run_block:
            continue
        for flag in FLAG_RE.findall(run_block):
            assert flag in help_flags["run"], (
                f"action.yml: flag '{flag}' not in 'llm-regress run' --help"
            )
