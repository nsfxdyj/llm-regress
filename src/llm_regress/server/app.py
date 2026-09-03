from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import api_projects, api_runs, api_suites
from .db import Database


def create_app(db_path=None, client_factory=None) -> FastAPI:
    app = FastAPI(title="llm-regress")
    app.state.db = Database(db_path)
    app.state.client_factory = client_factory or _default_client_factory
    app.state.run_sync = False
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_projects.router, prefix="/api")
    app.include_router(api_suites.router, prefix="/api")
    app.include_router(api_runs.router, prefix="/api")
    return app


def _default_client_factory(suite):
    from .deps import make_clients

    return make_clients(suite)
