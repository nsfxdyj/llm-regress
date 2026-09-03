from __future__ import annotations

from pydantic import BaseModel


class ProjectIn(BaseModel):
    name: str


class ProjectOut(BaseModel):
    id: int
    name: str
    created_at: str


class SuiteIn(BaseModel):
    name: str
    yaml_text: str


class SuiteOut(BaseModel):
    id: int
    project_id: int
    name: str
    yaml_text: str
    updated_at: str


class ValidateOut(BaseModel):
    ok: bool
    cases: list[dict] = []
    error: str | None = None
