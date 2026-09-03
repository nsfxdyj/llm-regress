from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .db_models import Base


def default_db_path() -> Path:
    return Path.cwd() / ".llm-regress" / "server.db"


class Database:
    def __init__(self, path: str | Path | None = None):
        p = Path(path) if path else default_db_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        self.path = p
        self.engine = create_engine(
            f"sqlite:///{p}", connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
