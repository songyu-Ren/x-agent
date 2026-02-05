from __future__ import annotations

from app.celery_app import celery_app
from app.tasks import run_daily


def test_celery_run_daily_eager_returns_run_id(monkeypatch):
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    import app.tasks as tasks

    monkeypatch.setattr(tasks.orchestrator, "start_run", lambda source, run_id=None: str(run_id))

    res = run_daily.delay(run_id="run_test", source="manual")
    assert res.get(timeout=5) == "run_test"
