from __future__ import annotations

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(unique=True)
    created_at: Mapped[str]

    suites: Mapped[list["Suite"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Suite(Base):
    __tablename__ = "suites"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str]
    yaml_text: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[str]

    project: Mapped[Project] = relationship(back_populates="suites")
    runs: Mapped[list["Run"]] = relationship(
        back_populates="suite", cascade="all, delete-orphan", order_by="Run.id.desc()"
    )
    baseline: Mapped["Baseline | None"] = relationship(
        back_populates="suite", cascade="all, delete-orphan", uselist=False
    )


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    suite_id: Mapped[int] = mapped_column(ForeignKey("suites.id"))
    status: Mapped[str] = mapped_column(default="pending")  # pending|running|done|error
    result_json: Mapped[str | None] = mapped_column(Text, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[str]
    finished_at: Mapped[str | None] = mapped_column(default=None)

    suite: Mapped[Suite] = relationship(back_populates="runs")


class Baseline(Base):
    __tablename__ = "baselines"

    suite_id: Mapped[int] = mapped_column(ForeignKey("suites.id"), primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    created_at: Mapped[str]

    suite: Mapped[Suite] = relationship(back_populates="baseline")
    run: Mapped[Run] = relationship()
