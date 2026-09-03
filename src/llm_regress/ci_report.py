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
            if delta is not None and delta.old_score is not None and delta.new_score is not None:
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


# File-producing formats: name -> renderer(run, comparison) -> str.
# Later tasks register "html" here; "github" is stdout-producing and gets
# its own dispatch branch in emit_reports (see _STDOUT_FORMATS).
_FILE_RENDERERS: dict[str, Callable[[RunResult, Comparison | None], str]] = {
    "junit": render_junit,
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
