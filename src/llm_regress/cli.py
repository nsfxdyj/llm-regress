# src/llm_regress/cli.py
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import typer

from .baseline import (
    Comparison,
    JudgeChangedError,
    baseline_path,
    compare,
    load_baseline,
    save_baseline,
)
from .ci_report import emit_reports, render_markdown_summary, validate_report_options
from .evaluators.factory import EvaluatorConfigError
from .github_api import COMMENT_MARKER, GitHubAPI, GitHubAPIError, find_bot_comment
from .models import CaseStatus, RunResult, TestSuite
from .providers.base import LLMClient, ProviderError
from .providers.openai_compat import OpenAICompatClient
from .report import render_console, write_run_json
from .runner import Runner
from .suite_loader import SuiteLoadError, load_suite

app = typer.Typer(help="llm-regress: LLM 应用回归测试（CI for prompts）")

EXAMPLE_SUITE = """\
name: my-suite
target:
  provider: openai-compatible
  base_url: https://api.deepseek.com
  api_key_env: DEEPSEEK_API_KEY
  model: deepseek-chat
# judge:            # 可选：单独指定裁判模型（更换裁判需重建基线）
#   base_url: https://api.deepseek.com
#   api_key_env: DEEPSEEK_API_KEY
#   model: deepseek-chat
cases:
  - id: example-greeting
    input: "用一句话介绍我们的产品 llm-regress"
    expected: "llm-regress 是一个 LLM 应用回归测试工具。"
    evaluators:
      - type: contains
        params: {keywords: ["llm-regress"]}
      - type: length
        params: {max_chars: 200}
      # - type: similarity
      #   params: {threshold: 0.8}
      # - type: judge
      #   params: {mode: absolute}
"""


def _make_clients(suite: TestSuite) -> tuple[LLMClient, LLMClient]:
    target = OpenAICompatClient(suite.target)
    judge = OpenAICompatClient(suite.judge) if suite.judge else target
    return target, judge


@app.command()
def init(path: Path = typer.Argument(Path("suite.yaml"), help="要生成的示例用例集路径")):
    if path.exists():
        typer.echo(f"File already exists: {path}", err=True)
        raise typer.Exit(code=3)
    path.write_text(EXAMPLE_SUITE, encoding="utf-8")
    typer.echo(f"Created {path}. Edit it, then run: llm-regress baseline {path}")


def _execute(
    suite_file: Path,
    concurrency: int,
    save: bool,
    formats: list[str],
    outputs: list[Path],
) -> int:
    if (msg := validate_report_options(formats, outputs)) is not None:
        typer.echo(msg, err=True)
        return 3
    try:
        suite = load_suite(suite_file)
        target, judge = _make_clients(suite)
    except (SuiteLoadError, ProviderError) as e:
        typer.echo(f"Config error: {e}", err=True)
        return 3
    runner = Runner(target, judge, concurrency=concurrency)
    try:
        run = asyncio.run(runner.run(suite))
    except EvaluatorConfigError as e:
        typer.echo(f"Config error: {e}", err=True)
        return 3
    run_path = write_run_json(run, Path.cwd())
    typer.echo(f"Run recorded: {run_path}")

    root = Path.cwd()
    comparison: Comparison | None = None
    exit_code = 0
    if save:
        save_baseline(run, root)
        typer.echo(render_console(run))
        typer.echo(f"Baseline saved: {baseline_path(suite.name, root)}")
    else:
        bp = baseline_path(suite.name, root)
        if bp.exists():
            baseline = load_baseline(bp)
            try:
                comparison = compare(run, baseline)
            except JudgeChangedError as e:
                typer.echo(str(e), err=True)
                return 3
            typer.echo(render_console(run, comparison))
            if comparison.has_regressions:
                exit_code = 1
        else:
            typer.echo(render_console(run))
            typer.echo(f"No baseline at {bp}; run `llm-regress baseline {suite_file}` to create one.")
    if exit_code == 0 and any(r.status == CaseStatus.ERROR for r in run.results):
        exit_code = 2
    override = emit_reports(
        run, comparison, formats, outputs, err=lambda m: typer.echo(m, err=True)
    )
    return override if override is not None else exit_code


@app.command()
def run(
    suite_file: Path = typer.Argument(..., help="用例集 YAML 路径"),
    save_baseline: bool = typer.Option(False, "--save-baseline", help="运行并把结果保存为新基线"),
    concurrency: int = typer.Option(4, "--concurrency", "-c", min=1, help="并发调用上限"),
    formats: list[str] = typer.Option(["console"], "--format", help="报告格式，可重复传入：console|junit|github|html"),
    outputs: list[Path] = typer.Option([], "--output", help="报告输出路径，可重复；按顺序与文件类 --format（junit/html）一一配对"),
):
    raise typer.Exit(code=_execute(suite_file, concurrency, save_baseline, formats, outputs))


@app.command()
def baseline(
    suite_file: Path = typer.Argument(..., help="用例集 YAML 路径"),
    concurrency: int = typer.Option(4, "--concurrency", "-c", min=1, help="并发调用上限"),
    formats: list[str] = typer.Option(["console"], "--format", help="报告格式，可重复传入：console|junit|github|html"),
    outputs: list[Path] = typer.Option([], "--output", help="报告输出路径，可重复；按顺序与文件类 --format（junit/html）一一配对"),
):
    """运行用例集并把结果保存为基线。"""
    raise typer.Exit(code=_execute(suite_file, concurrency, save=True, formats=formats, outputs=outputs))


def _post_comment(repo: str, pr: int, run_file: Path) -> int:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        typer.echo(
            "GITHUB_TOKEN environment variable is not set; "
            "export a token with pull-requests/issues write access.",
            err=True,
        )
        return 3
    try:
        run = RunResult.model_validate_json(run_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        typer.echo(f"Failed to load run file {run_file}: {e}", err=True)
        return 3

    comparison: Comparison | None = None
    warning = ""
    bp = baseline_path(run.suite_name, Path.cwd())
    if bp.exists():
        try:
            baseline = load_baseline(bp)
        except (OSError, ValueError) as e:
            # Unreadable/corrupt baseline (OSError for IO failures; ValueError
            # for invalid JSON / schema mismatch — pydantic ValidationError
            # subclasses ValueError): degrade to no-comparison and warn at the
            # top of the comment body — never fail the comment.
            typer.echo(f"Corrupt baseline {bp}: {e}", err=True)
            warning = "> ⚠️ 基线文件损坏，已按无对比模式生成评论\n\n"
        else:
            try:
                comparison = compare(run, baseline)
            except JudgeChangedError as e:
                # Judge fingerprint mismatch: degrade to no-comparison and warn at
                # the top of the comment body — never fail the comment.
                typer.echo(str(e), err=True)
                warning = f"> ⚠️ {e}\n\n"
    body = warning + render_markdown_summary(run, comparison) + f"\n\n{COMMENT_MARKER}"

    api = GitHubAPI(token)
    try:
        existing = find_bot_comment(api.list_comments(repo, pr))
        if existing is not None:
            resp = api.update_comment(repo, existing, body)
        else:
            resp = api.create_comment(repo, pr, body)
    except GitHubAPIError as e:
        typer.echo(
            f"GitHub API error (status {e.status}): {e.body[:500]}", err=True
        )
        return 3
    typer.echo(f"Comment posted: {resp.get('html_url', '')}")
    return 0


@app.command()
def comment(
    repo: str = typer.Option(..., "--repo", help="仓库，形如 owner/name"),
    pr: int = typer.Option(..., "--pr", min=1, help="Pull Request 编号"),
    run_file: Path = typer.Option(..., "--run-file", help="运行结果 JSON（.llm-regress/runs/xxx.json）"),
):
    """把运行结果作为评论发布（或幂等更新）到 GitHub PR。"""
    raise typer.Exit(code=_post_comment(repo, pr, run_file))
