# src/llm_regress/ci_report.py
"""CI-oriented report renderers and the report-dispatch seam.

New formats plug in by registering a renderer in ``_FILE_RENDERERS`` (or a
future stdout-producing registry for ``github``); the CLI plumbing stays
unchanged. All XML is built with ``xml.etree.ElementTree`` — never
hand-concatenated — so attribute escaping is automatic.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable
from xml.etree import ElementTree as ET

from .baseline import Comparison
from .models import CaseStatus, RunResult

CONSOLE_FORMAT = "console"

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


# File-producing formats: name -> renderer(run, comparison) -> str.
# Later tasks register "html" here; "github" is stdout-producing and will
# get its own dispatch branch in emit_reports.
_FILE_RENDERERS: dict[str, Callable[[RunResult, Comparison | None], str]] = {
    "junit": render_junit,
}


def validate_report_options(formats: list[str], outputs: list[Path]) -> str | None:
    """Validate --format/--output pairing. Returns an error message or None.

    Format-agnostic: any format not in ``_FILE_RENDERERS`` (and not
    ``console``) is unknown; every file-producing format consumes exactly one
    ``--output``, paired in order.
    """
    unknown = [f for f in formats if f != CONSOLE_FORMAT and f not in _FILE_RENDERERS]
    if unknown:
        supported = ", ".join([CONSOLE_FORMAT, *_FILE_RENDERERS])
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
        if fmt not in _FILE_RENDERERS:
            continue
        path = next(pending)
        try:
            path.write_text(_FILE_RENDERERS[fmt](run, comparison), encoding="utf-8")
        except OSError as e:
            err(f"Failed to write {fmt} report to {path}: {e}")
            return 3
    return None
