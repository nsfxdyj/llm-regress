from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .baseline import Comparison
from .models import CaseStatus, RunResult


def write_run_json(run: RunResult, root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = root / ".llm-regress" / "runs" / f"{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    return path


def render_console(run: RunResult, comparison: Comparison | None = None) -> str:
    delta_by_id = {d.case_id: d for d in comparison.deltas} if comparison else {}
    lines = [f"Suite: {run.suite_name}  ({run.started_at})"]
    for r in run.results:
        if r.status == CaseStatus.ERROR:
            lines.append(f"  ✗ {r.case_id}: ERROR - {r.error}")
            continue
        mark = "✓" if r.passed else "✗"
        line = f"  {mark} {r.case_id}: score={r.score:.2f}"
        d = delta_by_id.get(r.case_id)
        if d and d.change == "regression":
            line += f"  REGRESSION (baseline {d.old_score:.2f})"
        elif d and d.change == "improved":
            line += f"  improved (baseline {d.old_score:.2f})"
        elif d and d.change == "new":
            line += "  (new case)"
        lines.append(line)
        for e in r.evals:
            if not e.passed:
                lines.append(f"      [{e.evaluator}] {e.detail}")
    if comparison:
        lines.append(f"Summary: {comparison.summary()}")
    else:
        passed = sum(1 for r in run.results if r.passed)
        errors = sum(1 for r in run.results if r.status == CaseStatus.ERROR)
        lines.append(f"Summary: {passed}/{len(run.results)} passed, {errors} errors")
    return "\n".join(lines)
