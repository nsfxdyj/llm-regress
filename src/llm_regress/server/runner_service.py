from __future__ import annotations

from datetime import datetime, timezone

from ..evaluators.factory import EvaluatorConfigError
from ..providers.base import ProviderError
from ..runner import Runner
from ..suite_loader import SuiteLoadError, loads_suite
from . import db_models as m
from .db import Database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def execute_run(run_id: int, yaml_text: str, db: Database, client_factory) -> None:
    """执行一次运行并把结果写回 Run 行。所有失败都落为 status=error，绝不抛给调用方。"""
    with db.Session() as s:
        row = s.get(m.Run, run_id)
        if row is None:
            return
        row.status = "running"
        s.commit()
    try:
        suite = loads_suite(yaml_text, source="suite")
        target, judge = client_factory(suite)
        result = await Runner(target, judge).run(suite)
        with db.Session() as s:
            row = s.get(m.Run, run_id)
            row.status = "done"
            row.result_json = result.model_dump_json()
            row.finished_at = _now()
            s.commit()
    except (SuiteLoadError, EvaluatorConfigError, ProviderError) as e:
        with db.Session() as s:
            row = s.get(m.Run, run_id)
            row.status = "error"
            row.error = str(e)
            row.finished_at = _now()
            s.commit()
    except Exception as e:  # 防御：后台任务绝不裸崩
        with db.Session() as s:
            row = s.get(m.Run, run_id)
            row.status = "error"
            row.error = f"unexpected: {e}"
            row.finished_at = _now()
            s.commit()
