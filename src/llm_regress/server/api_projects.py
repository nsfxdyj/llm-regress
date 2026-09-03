from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError

from . import db_models as m
from .db import Database
from .deps import get_db
from .schemas import ProjectIn, ProjectOut

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Database = Depends(get_db)):
    with db.Session() as s:
        return s.query(m.Project).order_by(m.Project.id).all()


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectIn, db: Database = Depends(get_db)):
    with db.Session() as s:
        p = m.Project(name=body.name, created_at=_now())
        s.add(p)
        try:
            s.commit()
        except IntegrityError:
            s.rollback()
            raise HTTPException(422, f"project name already exists: {body.name}")
        return p


@router.delete("/projects/{pid}", status_code=204)
def delete_project(pid: int, db: Database = Depends(get_db)):
    with db.Session() as s:
        p = s.get(m.Project, pid)
        if p is None:
            raise HTTPException(404, "project not found")
        s.delete(p)
        s.commit()
