from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from ..baseline import JudgeChangedError, compare
from ..models import CaseStatus, RunResult
from . import db_models as m
from .db import Database
from .deps import get_db
from .runner_service import execute_run

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _summary(result: RunResult) -> dict:
    total = len(result.results)
    passed = sum(1 for r in result.results if r.passed)
    errors = sum(1 for r in result.results if r.status == CaseStatus.ERROR)
    return {"total": total, "passed": passed, "errors": errors}


def _run_out(row: m.Run) -> dict:
    summary = None
    if row.status == "done" and row.result_json:
        summary = _summary(RunResult.model_validate_json(row.result_json))
    return {
        "id": row.id,
        "suite_id": row.suite_id,
        "status": row.status,
        "created_at": row.created_at,
        "finished_at": row.finished_at,
        "summary": summary,
    }


@router.post("/suites/{sid}/runs", status_code=202)
async def trigger_run(sid: int, request: Request, db: Database = Depends(get_db)):
    with db.Session() as s:
        suite = s.get(m.Suite, sid)
        if suite is None:
            raise HTTPException(404, "suite not found")
        run = m.Run(suite_id=sid, status="pending", created_at=_now())
        s.add(run)
        s.commit()
        run_id = run.id
        yaml_text = suite.yaml_text
    factory = request.app.state.client_factory
    if request.app.state.run_sync:
        await execute_run(run_id, yaml_text, db, factory)
    else:
        asyncio.create_task(execute_run(run_id, yaml_text, db, factory))
    return {"run_id": run_id}


@router.get("/suites/{sid}/runs")
def list_runs(sid: int, db: Database = Depends(get_db)):
    with db.Session() as s:
        if s.get(m.Suite, sid) is None:
            raise HTTPException(404, "suite not found")
        rows = s.query(m.Run).filter_by(suite_id=sid).order_by(m.Run.id.desc()).all()
        return [_run_out(r) for r in rows]


@router.get("/runs/{rid}")
def get_run(rid: int, db: Database = Depends(get_db)):
    with db.Session() as s:
        row = s.get(m.Run, rid)
        if row is None:
            raise HTTPException(404, "run not found")
        out = _run_out(row)
        out["error"] = row.error
        out["result"] = None
        out["comparison"] = None
        out["judge_changed"] = False
        if row.status != "done" or not row.result_json:
            return out
        result = RunResult.model_validate_json(row.result_json)
        out["result"] = result.model_dump()
        baseline = s.get(m.Baseline, row.suite_id)
        if baseline is None:
            return out
        base_run = s.get(m.Run, baseline.run_id)
        if base_run is None or not base_run.result_json:
            return out
        base_result = RunResult.model_validate_json(base_run.result_json)
        try:
            comp = compare(result, base_result)
        except JudgeChangedError:
            out["judge_changed"] = True
            return out
        out["comparison"] = {
            "has_regressions": comp.has_regressions,
            "has_errors": comp.has_errors,
            "summary": comp.summary(),
            "deltas": [vars(d) for d in comp.deltas],
            "baseline_run_id": baseline.run_id,
        }
        return out


@router.post("/runs/{rid}/promote")
def promote_run(rid: int, db: Database = Depends(get_db)):
    with db.Session() as s:
        row = s.get(m.Run, rid)
        if row is None:
            raise HTTPException(404, "run not found")
        if row.status != "done":
            raise HTTPException(422, "only a finished run can be promoted to baseline")
        existing = s.get(m.Baseline, row.suite_id)
        if existing is None:
            s.add(m.Baseline(suite_id=row.suite_id, run_id=rid, created_at=_now()))
        else:
            existing.run_id = rid
            existing.created_at = _now()
        s.commit()
        return {"suite_id": row.suite_id, "baseline_run_id": rid}


@router.get("/suites/{sid}/baseline")
def get_baseline(sid: int, db: Database = Depends(get_db)):
    with db.Session() as s:
        if s.get(m.Suite, sid) is None:
            raise HTTPException(404, "suite not found")
        baseline = s.get(m.Baseline, sid)
        if baseline is None:
            return {"suite_id": sid, "baseline_run_id": None}
        return {
            "suite_id": sid,
            "baseline_run_id": baseline.run_id,
            "created_at": baseline.created_at,
        }
