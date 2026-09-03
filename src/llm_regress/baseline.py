# src/llm_regress/baseline.py
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .models import CaseStatus, RunResult


class JudgeChangedError(Exception):
    """裁判模型与基线绑定的不一致，历史对比失效。"""

    def __init__(self, old: str | None, new: str | None):
        self.old = old
        self.new = new
        super().__init__(
            f"Judge changed ({old} -> {new}); baseline comparison invalid. Re-baseline required."
        )


def baseline_path(suite_name: str, root: Path) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", suite_name)
    return root / ".llm-regress" / "baselines" / f"{safe}.json"


def save_baseline(run: RunResult, root: Path) -> Path:
    path = baseline_path(run.suite_name, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_baseline(path: Path) -> RunResult:
    return RunResult.model_validate_json(path.read_text(encoding="utf-8"))


@dataclass
class CaseDelta:
    case_id: str
    old_score: float | None
    new_score: float | None
    change: str  # regression | improved | unchanged | new | removed | error


@dataclass
class Comparison:
    deltas: list[CaseDelta]

    @property
    def has_regressions(self) -> bool:
        return any(d.change == "regression" for d in self.deltas)

    @property
    def has_errors(self) -> bool:
        return any(d.change == "error" for d in self.deltas)

    def summary(self) -> str:
        counts: dict[str, int] = {}
        for d in self.deltas:
            counts[d.change] = counts.get(d.change, 0) + 1
        return ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) or "no cases"


def compare(
    run: RunResult,
    baseline: RunResult,
    *,
    regression_threshold: float = 0.1,
) -> Comparison:
    if run.judge_fingerprint != baseline.judge_fingerprint:
        raise JudgeChangedError(old=baseline.judge_fingerprint, new=run.judge_fingerprint)
    old_by_id = {r.case_id: r for r in baseline.results}
    new_by_id = {r.case_id: r for r in run.results}
    deltas: list[CaseDelta] = []
    for cid, new in new_by_id.items():
        old = old_by_id.get(cid)
        if old is None:
            deltas.append(CaseDelta(cid, None, new.score, "new"))
            continue
        if new.status == CaseStatus.ERROR:
            deltas.append(CaseDelta(cid, old.score, None, "error"))
            continue
        if old.passed and not new.passed:
            change = "regression"
        elif old.score - new.score > regression_threshold:
            change = "regression"
        elif new.score - old.score > regression_threshold:
            change = "improved"
        else:
            change = "unchanged"
        deltas.append(CaseDelta(cid, old.score, new.score, change))
    for cid, old in old_by_id.items():
        if cid not in new_by_id:
            deltas.append(CaseDelta(cid, old.score, None, "removed"))
    return Comparison(deltas=deltas)
