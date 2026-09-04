# src/llm_regress/ci_report.py
"""CI-oriented report renderers and the report-dispatch seam.

New file-producing formats plug in by registering a renderer in
``_FILE_RENDERERS``; stdout-producing formats (``github``) are dispatched in
their own branch of ``emit_reports``. The CLI plumbing stays unchanged. All
XML is built with ``xml.etree.ElementTree`` — never hand-concatenated — so
attribute escaping is automatic.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree as ET

from .baseline import Comparison
from .models import CaseStatus, RunResult

CONSOLE_FORMAT = "console"
GITHUB_FORMAT = "github"

XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>'


def render_junit(run: RunResult, comparison: Comparison | None = None) -> str:
    """Render a JUnit XML report for one run.

    - error cases -> ``<error>``, failed cases -> ``<failure>`` (with the
      failing evaluators listed in the element text), passed cases -> empty
      ``<testcase>``.
    - ``comparison`` only supplies baseline scores for failure messages;
      ``removed`` deltas never appear (the run did not execute them) and
      ``new`` cases are rendered normally from ``run.results``.
    """
    delta_by_id = {d.case_id: d for d in comparison.deltas} if comparison else {}
    errors = sum(1 for r in run.results if r.status == CaseStatus.ERROR)
    failures = sum(
        1 for r in run.results if r.status != CaseStatus.ERROR and not r.passed
    )
    suite = ET.Element(
        "testsuite",
        {
            "name": run.suite_name,
            "tests": str(len(run.results)),
            "failures": str(failures),
            "errors": str(errors),
            "timestamp": run.started_at,
        },
    )
    for r in run.results:
        case = ET.SubElement(
            suite, "testcase", {"name": r.case_id, "classname": run.suite_name}
        )
        if r.status == CaseStatus.ERROR:
            ET.SubElement(case, "error", {"message": r.error or "unknown error"})
        elif not r.passed:
            delta = delta_by_id.get(r.case_id)
            if (
                delta is not None
                and delta.change == "regression"
                and delta.old_score is not None
                and delta.new_score is not None
            ):
                message = (
                    f"score {delta.new_score:.2f} below baseline {delta.old_score:.2f}"
                )
            else:
                message = f"failed, score {r.score:.2f}"
            failure = ET.SubElement(case, "failure", {"message": message})
            failure.text = "\n".join(
                f"[{e.evaluator}] {e.detail}" for e in r.evals if not e.passed
            )
    return f"{XML_DECLARATION}\n{ET.tostring(suite, encoding='unicode')}"


def _escape_annotation(text: str) -> str:
    """Escape text for GitHub Actions annotation commands.

    ``%`` must be replaced first so the introduced escapes are not
    re-escaped. Applied to every interpolated value (case_id, error, ...).
    """
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def render_github_annotations(run: RunResult, comparison: Comparison | None = None) -> str:
    """Render GitHub Actions ``::error`` workflow commands, one per line.

    - error cases -> ``::error title=llm-regress error::...``
    - regressions -> ``::error title=llm-regress regression::...`` (takes
      precedence over the plain-failure line for the same case)
    - other failed cases -> ``::error title=llm-regress::...``
    Passing cases produce no output; an all-passing run renders ``""``.
    """
    delta_by_id = {d.case_id: d for d in comparison.deltas} if comparison else {}
    lines: list[str] = []
    for r in run.results:
        cid = _escape_annotation(r.case_id)
        if r.status == CaseStatus.ERROR:
            message = _escape_annotation(r.error or "unknown error")
            lines.append(f"::error title=llm-regress error::{cid} {message}")
            continue
        delta = delta_by_id.get(r.case_id)
        if (
            delta is not None
            and delta.change == "regression"
            and delta.old_score is not None
            and delta.new_score is not None
        ):
            lines.append(
                f"::error title=llm-regress regression::{cid} "
                f"{delta.old_score:.2f} -> {delta.new_score:.2f}"
            )
        elif not r.passed:
            lines.append(
                f"::error title=llm-regress::{cid} failed, score {r.score:.2f}"
            )
    return "\n".join(lines)


_CHANGE_LABELS = {
    "regression": "回归",
    "improved": "改善",
    "unchanged": "不变",
    "new": "新增",
    "error": "错误",
}


def render_markdown_summary(run: RunResult, comparison: Comparison | None = None) -> str:
    """Render the GitHub Job Summary / PR-comment markdown body.

    Pure function of (run, comparison) so the ``comment`` command can reuse
    it verbatim as the comment body. Structure: heading, suite metadata,
    regression alert (when any), results table, ``Summary:`` line. ``removed``
    deltas are skipped — the run did not execute those cases.
    """
    delta_by_id = {d.case_id: d for d in comparison.deltas} if comparison else {}
    lines = [
        "## llm-regress 报告",
        "",
        f"- 套件: {run.suite_name}",
        f"- 时间: {run.started_at}",
        f"- Target 指纹: {run.target_fingerprint}",
        "",
    ]
    if comparison and comparison.has_regressions:
        n = sum(1 for d in comparison.deltas if d.change == "regression")
        lines.append(f"> ❌ 检测到 {n} 个回归")
        lines.append("")
    lines.append("| 用例 | 结果 | 分数 | 基线 | 变化 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for r in run.results:
        cid = r.case_id.replace("|", "\\|")
        delta = delta_by_id.get(r.case_id)
        baseline_cell = (
            f"{delta.old_score:.2f}" if delta and delta.old_score is not None else "-"
        )
        change_cell = (
            _CHANGE_LABELS.get(delta.change, delta.change) if delta else "-"
        )
        if r.status == CaseStatus.ERROR:
            result_cell, score_cell = "⚠️ 错误", "-"
        elif r.passed:
            result_cell, score_cell = "✅ 通过", f"{r.score:.2f}"
        else:
            result_cell, score_cell = "❌ 失败", f"{r.score:.2f}"
        lines.append(
            f"| {cid} | {result_cell} | {score_cell} | {baseline_cell} | {change_cell} |"
        )
    lines.append("")
    if comparison:
        lines.append(f"Summary: {comparison.summary()}")
    else:
        passed = sum(1 for r in run.results if r.passed)
        errors = sum(1 for r in run.results if r.status == CaseStatus.ERROR)
        lines.append(f"Summary: {passed}/{len(run.results)} passed, {errors} errors")
    return "\n".join(lines)


# --- Standalone HTML report (M4-T3) ---------------------------------------

_HTML_STYLE = """\
:root{--fg:#24292f;--muted:#6a737d;--line:#e3e6eb;--bg:#f5f6f8;
--ok:#2da44e;--bad:#cf222e;--warn:#bf8700;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);line-height:1.6;
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace}
.wrap{max-width:920px;margin:0 auto;padding:32px 20px 64px}
header h1{font-size:22px;margin:0 0 6px}
.meta{color:var(--muted);font-size:13px}
.meta .mono{background:#fff;border:1px solid var(--line);border-radius:4px;padding:0 5px}
.summary{display:flex;gap:12px;flex-wrap:wrap;margin:22px 0 28px}
.stat{flex:1;min-width:110px;background:#fff;border:1px solid var(--line);border-radius:8px;padding:12px 16px}
.stat .num{font-size:26px;font-weight:600;line-height:1.2}
.stat .label{font-size:12px;color:var(--muted)}
.stat.ok .num{color:var(--ok)}
.stat.reg .num{color:var(--bad)}
.stat.err .num{color:var(--warn)}
.card{background:#fff;border:1px solid var(--line);border-left:4px solid var(--line);
border-radius:8px;padding:16px 20px;margin-bottom:16px}
.card.s-ok{border-left-color:var(--ok)}
.card.s-reg,.card.s-fail{border-left-color:var(--bad)}
.card.s-err{border-left-color:var(--warn)}
.card-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.case-id{font-weight:600;font-size:15px}
.badge{font-size:12px;padding:2px 10px;border-radius:999px;font-weight:600}
.badge.ok{background:#e6f4ea;color:var(--ok)}
.badge.bad{background:#fdeceb;color:var(--bad)}
.badge.warn{background:#fdf3dd;color:var(--warn)}
.chip{font-size:12px;padding:2px 8px;border-radius:999px;background:#eef1f4;color:var(--muted)}
.score{margin-left:auto;color:var(--muted);font-size:14px}
.score .mono{color:var(--fg);font-weight:600}
.field{margin-top:12px}
.field .label{font-size:12px;color:var(--muted);margin-bottom:4px}
pre{margin:0;background:#f6f8fa;border:1px solid var(--line);border-radius:6px;
padding:10px 12px;white-space:pre-wrap;word-break:break-word;font-size:13px;
font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace}
ul.evals{margin:6px 0 0;padding-left:20px;font-size:13px}
ul.evals li{margin:2px 0}
details{margin-top:12px}
summary{cursor:pointer;color:var(--muted);font-size:13px}
footer{margin-top:36px;color:var(--muted);font-size:12px;text-align:center}
"""


def _html_field(label: str, text: str) -> str:
    """One labelled <pre> block; ``text`` must already be escaped."""
    return (
        f'<div class="field"><div class="label">{label}</div>'
        f"<pre>{text}</pre></div>"
    )


def _render_case_card(run: RunResult, r, delta) -> str:
    """Render one case card. Every embedded text fragment is html-escaped."""
    import html as _html

    esc = _html.escape
    is_error = r.status == CaseStatus.ERROR
    is_regression = (
        delta is not None
        and delta.change == "regression"
        and r.status != CaseStatus.ERROR
    )
    if is_error:
        state, badge_cls, badge = "s-err", "warn", "错误"
    elif is_regression:
        state, badge_cls, badge = "s-reg", "bad", "回归"
    elif not r.passed:
        state, badge_cls, badge = "s-fail", "bad", "失败"
    else:
        state, badge_cls, badge = "s-ok", "ok", "通过"

    if is_error:
        score_html = '<span class="mono">—</span>'
    elif delta is not None and delta.old_score is not None and delta.new_score is not None:
        score_html = (
            f'<span class="mono">{delta.old_score:.2f} → {delta.new_score:.2f}</span>'
        )
    else:
        score_html = f'<span class="mono">{r.score:.2f}</span>'

    chip = ""
    if delta is not None and delta.change in ("improved", "new", "unchanged"):
        chip = f'<span class="chip">{_CHANGE_LABELS[delta.change]}</span>'

    parts = [
        f'<section class="card {state}">',
        '<div class="card-head">',
        f'<span class="case-id mono">{esc(r.case_id)}</span>',
        f'<span class="badge {badge_cls}">{badge}</span>',
        chip,
        f'<span class="score">分数 {score_html}</span>',
        "</div>",
    ]
    if r.input:
        parts.append(_html_field("输入", esc(r.input)))
    if is_error:
        parts.append(_html_field("错误信息", esc(r.error or "unknown error")))
    else:
        parts.append(_html_field("模型输出", esc(r.output)))
    if r.expected:
        parts.append(_html_field("期望输出", esc(r.expected)))
    failing = [e for e in r.evals if not e.passed]
    if failing:
        items = "".join(
            f'<li><span class="mono">[{esc(e.evaluator)}]</span> {esc(e.detail)}</li>'
            for e in failing
        )
        parts.append(
            f'<div class="field"><div class="label">失败评测明细</div>'
            f'<ul class="evals">{items}</ul></div>'
        )
    for e in r.evals:
        if e.raw:
            parts.append(
                f"<details><summary>裁判原始输出 · "
                f'<span class="mono">{esc(e.evaluator)}</span></summary>'
                f"<pre>{esc(e.raw)}</pre></details>"
            )
    parts.append("</section>")
    return "\n".join(p for p in parts if p)


def render_html(run: RunResult, comparison: Comparison | None = None) -> str:
    """Render a standalone single-file HTML report for one run.

    Inline ``<style>`` only — no external resources, no JS. Every piece of
    embedded text (case_id, input, output, expected, error, evaluator
    details, judge raw output) goes through ``html.escape``; model output
    may contain arbitrary markup. ``removed`` deltas are skipped — the run
    did not execute those cases.
    """
    import html as _html

    esc = _html.escape
    delta_by_id = {d.case_id: d for d in comparison.deltas} if comparison else {}
    total = len(run.results)
    passed_n = sum(
        1 for r in run.results if r.status != CaseStatus.ERROR and r.passed
    )
    error_n = sum(1 for r in run.results if r.status == CaseStatus.ERROR)
    reg_n = (
        sum(1 for d in comparison.deltas if d.change == "regression")
        if comparison
        else 0
    )
    cards = "\n".join(
        _render_case_card(run, r, delta_by_id.get(r.case_id)) for r in run.results
    )
    judge_line = ""
    if run.judge_fingerprint:
        judge_line = (
            f' · Judge 指纹 <span class="mono">{esc(run.judge_fingerprint)}</span>'
        )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>llm-regress 报告 · {esc(run.suite_name)}</title>
<style>
{_HTML_STYLE}
</style>
</head>
<body>
<div class="wrap">
<header>
<h1>llm-regress 报告</h1>
<div class="meta">套件 <span class="mono">{esc(run.suite_name)}</span>
· 开始时间 <span class="mono">{esc(run.started_at)}</span>
· Target 指纹 <span class="mono">{esc(run.target_fingerprint)}</span>{judge_line}</div>
</header>
<section class="summary">
<div class="stat ok"><div class="num">{passed_n}</div><div class="label">通过</div></div>
<div class="stat reg"><div class="num">{reg_n}</div><div class="label">回归</div></div>
<div class="stat err"><div class="num">{error_n}</div><div class="label">错误</div></div>
<div class="stat"><div class="num">{total}</div><div class="label">总计</div></div>
</section>
{cards}
<footer>由 llm-regress 生成的独立报告</footer>
</div>
</body>
</html>
"""


# File-producing formats: name -> renderer(run, comparison) -> str.
# "github" is stdout-producing and gets its own dispatch branch in
# emit_reports (see _STDOUT_FORMATS).
_FILE_RENDERERS: dict[str, Callable[[RunResult, Comparison | None], str]] = {
    "junit": render_junit,
    "html": render_html,
}

# Stdout-producing formats (annotations to stdout instead of a report file).
_STDOUT_FORMATS = {GITHUB_FORMAT}


def validate_report_options(formats: list[str], outputs: list[Path]) -> str | None:
    """Validate --format/--output pairing. Returns an error message or None.

    Format-agnostic: any format not in ``_FILE_RENDERERS`` (and not
    ``console``) is unknown; every file-producing format consumes exactly one
    ``--output``, paired in order.
    """
    unknown = [
        f
        for f in formats
        if f != CONSOLE_FORMAT
        and f not in _FILE_RENDERERS
        and f not in _STDOUT_FORMATS
    ]
    if unknown:
        supported = ", ".join([CONSOLE_FORMAT, *_FILE_RENDERERS, *_STDOUT_FORMATS])
        return (
            f"Unknown report format(s): {', '.join(unknown)} "
            f"(supported: {supported})"
        )
    file_formats = [f for f in formats if f in _FILE_RENDERERS]
    if len(outputs) != len(file_formats):
        names = ", ".join(file_formats) or "none"
        return (
            f"--output count ({len(outputs)}) does not match file-producing "
            f"--format count ({len(file_formats)}: {names}); pair them in order, "
            f"e.g. --format junit --output report.xml"
        )
    return None


def emit_reports(
    run: RunResult,
    comparison: Comparison | None,
    formats: list[str],
    outputs: list[Path],
    err: Callable[[str], None],
) -> int | None:
    """Dispatch report formats for a finished run.

    ``console`` output is printed by the CLI itself and skipped here.
    Returns an exit-code override (3) on any failure, else None so the
    caller keeps the run's own exit code.
    """
    if (msg := validate_report_options(formats, outputs)) is not None:
        err(msg)
        return 3
    pending = iter(outputs)
    for fmt in formats:
        if fmt == GITHUB_FORMAT:
            # Annotations go to stdout (after the CLI's console output);
            # the markdown summary is appended to $GITHUB_STEP_SUMMARY when
            # the variable points to a writable file. A missing variable is
            # the local-run scenario — silently skip, not an error.
            annotations = render_github_annotations(run, comparison)
            if annotations:
                print(annotations)
            summary_env = os.environ.get("GITHUB_STEP_SUMMARY")
            if summary_env:
                try:
                    with open(summary_env, "a", encoding="utf-8") as f:
                        f.write(render_markdown_summary(run, comparison) + "\n")
                except OSError as e:
                    err(f"Failed to append GitHub step summary to {summary_env}: {e}")
                    return 3
            continue
        if fmt not in _FILE_RENDERERS:
            continue
        path = next(pending)
        try:
            path.write_text(_FILE_RENDERERS[fmt](run, comparison), encoding="utf-8")
        except OSError as e:
            err(f"Failed to write {fmt} report to {path}: {e}")
            return 3
    return None
