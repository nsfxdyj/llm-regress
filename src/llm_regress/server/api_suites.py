from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError

from ..suite_loader import SuiteLoadError, loads_suite
from . import db_models as m
from .db import Database
from .deps import get_db
from .schemas import SuiteIn, SuiteOut, ValidateOut

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_or_422(yaml_text: str) -> None:
    try:
        loads_suite(yaml_text, source="suite")
    except SuiteLoadError as e:
        raise HTTPException(422, str(e))


@router.get("/projects/{pid}/suites", response_model=list[SuiteOut])
def list_suites(pid: int, db: Database = Depends(get_db)):
    with db.Session() as s:
        if s.get(m.Project, pid) is None:
            raise HTTPException(404, "project not found")
        return s.query(m.Suite).filter_by(project_id=pid).order_by(m.Suite.id).all()


@router.post("/projects/{pid}/suites", response_model=SuiteOut, status_code=201)
def create_suite(pid: int, body: SuiteIn, db: Database = Depends(get_db)):
    _parse_or_422(body.yaml_text)
    with db.Session() as s:
        if s.get(m.Project, pid) is None:
            raise HTTPException(404, "project not found")
        suite = m.Suite(project_id=pid, name=body.name, yaml_text=body.yaml_text, updated_at=_now())
        s.add(suite)
        try:
            s.commit()
        except IntegrityError:
            s.rollback()
            raise HTTPException(422, f"suite name already exists in project: {body.name}")
        return suite


@router.get("/suites/{sid}", response_model=SuiteOut)
def get_suite(sid: int, db: Database = Depends(get_db)):
    with db.Session() as s:
        suite = s.get(m.Suite, sid)
        if suite is None:
            raise HTTPException(404, "suite not found")
        return suite


@router.put("/suites/{sid}", response_model=SuiteOut)
def update_suite(sid: int, body: SuiteIn, db: Database = Depends(get_db)):
    _parse_or_422(body.yaml_text)
    with db.Session() as s:
        suite = s.get(m.Suite, sid)
        if suite is None:
            raise HTTPException(404, "suite not found")
        suite.name = body.name
        suite.yaml_text = body.yaml_text
        suite.updated_at = _now()
        try:
            s.commit()
        except IntegrityError:
            s.rollback()
            raise HTTPException(422, f"suite name already exists in project: {body.name}")
        return suite


@router.delete("/suites/{sid}", status_code=204)
def delete_suite(sid: int, db: Database = Depends(get_db)):
    with db.Session() as s:
        suite = s.get(m.Suite, sid)
        if suite is None:
            raise HTTPException(404, "suite not found")
        s.delete(suite)
        s.commit()


@router.post("/suites/{sid}/validate", response_model=ValidateOut)
def validate_suite_endpoint(sid: int, db: Database = Depends(get_db)):
    with db.Session() as s:
        suite = s.get(m.Suite, sid)
        if suite is None:
            raise HTTPException(404, "suite not found")
        text = suite.yaml_text
    try:
        parsed = loads_suite(text, source="suite")
    except SuiteLoadError as e:
        return ValidateOut(ok=False, error=str(e))
    return ValidateOut(
        ok=True,
        cases=[{"id": c.id, "evaluator_count": len(c.evaluators)} for c in parsed.cases],
    )
