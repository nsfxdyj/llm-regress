from llm_regress.server.db import Database
from llm_regress.server.db_models import Baseline, Project, Run, Suite


def test_roundtrip(tmp_path):
    db = Database(tmp_path / "t.db")
    with db.Session() as s:
        p = Project(name="demo", created_at="2026-09-03T00:00:00+00:00")
        s.add(p)
        s.flush()
        suite = Suite(project_id=p.id, name="s1", yaml_text="name: x", updated_at="2026-09-03T00:00:00+00:00")
        s.add(suite)
        s.flush()
        run = Run(suite_id=suite.id, status="pending", created_at="2026-09-03T00:00:00+00:00")
        s.add(run)
        s.flush()
        s.add(Baseline(suite_id=suite.id, run_id=run.id, created_at="2026-09-03T00:00:00+00:00"))
        s.commit()

    with db.Session() as s:
        got = s.query(Suite).filter_by(name="s1").one()
        assert got.project.name == "demo"
        assert len(got.runs) == 1 and got.runs[0].status == "pending"
        assert got.baseline.run_id == got.runs[0].id


def test_cascade_delete(tmp_path):
    db = Database(tmp_path / "t.db")
    with db.Session() as s:
        p = Project(name="demo", created_at="t")
        s.add(p)
        s.flush()
        suite = Suite(project_id=p.id, name="s1", yaml_text="y", updated_at="t")
        s.add(suite)
        s.flush()
        s.add(Run(suite_id=suite.id, status="done", created_at="t"))
        s.commit()
        pid = p.id

    with db.Session() as s:
        s.delete(s.get(Project, pid))
        s.commit()
        assert s.query(Suite).count() == 0
        assert s.query(Run).count() == 0
