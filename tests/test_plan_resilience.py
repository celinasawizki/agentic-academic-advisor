"""Regression tests found while QA-testing the workflow on MySQL."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import orchestrator
from app.core.db import SessionLocal
from app.main import app
from app.models import PlanRun, ScheduleOption


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _plan(client):
    r = client.post("/api/plans", json={"student_id": "demo-lina"})
    plan = client.get(f"/api/plans/{r.json()['plan_id']}").json()
    assert plan["status"] == "complete", plan["state"].get("_error")
    return plan


def test_failed_run_with_broken_session_releases_plan(client, monkeypatch):
    """A run that dies with the session in an invalid transaction (e.g. a dropped MySQL
    connection) must still mark the plan failed; before, it stayed 'running' forever and
    every later change was refused with 409."""
    plan = _plan(client)

    def broken_run(db, plan_id, start_from):
        db.add(PlanRun(id=plan_id, student_id="demo-lina", term_id="x", status="pending", state={}))
        db.flush()  # duplicate primary key -> session needs rollback, like a lost connection

    monkeypatch.setattr(orchestrator, "_run", broken_run)
    r = client.post(f"/api/plans/{plan['id']}/regenerate")
    assert r.status_code == 200
    after = client.get(f"/api/plans/{plan['id']}?full=false").json()
    assert after["status"] == "failed" and after["state"]["_error"]
    monkeypatch.undo()
    assert client.post(f"/api/plans/{plan['id']}/regenerate").status_code == 200  # not stuck
    assert client.get(f"/api/plans/{plan['id']}?full=false").json()["status"] == "complete"


def test_option_from_earlier_iteration_is_removed_and_not_exportable(client):
    """Option ids are `{plan}-{strategy}`; when a strategy turns infeasible after a change, its
    old row used to survive and could be exported as a mock TUportal draft."""
    plan = _plan(client)
    stale_id = f"{plan['id']}-stale"
    with SessionLocal() as db:
        db.add(ScheduleOption(id=stale_id, plan_id=plan["id"], label="Old", strategy="graduation", rank=9,
                              total_credits=3, scores={}, violated_soft=[], review_status="checks_passed"))
        db.commit()
    r = client.post("/api/integration/tuportal/drafts", json={"plan_id": plan["id"], "option_id": stale_id, "student_approved": True})
    assert r.status_code == 409
    assert client.post(f"/api/plans/{plan['id']}/regenerate").status_code == 200
    with SessionLocal() as db:
        assert db.get(ScheduleOption, stale_id) is None
        ids = {o.id for o in db.query(ScheduleOption).filter_by(plan_id=plan["id"])}
    current = {o["id"] for o in client.get(f"/api/plans/{plan['id']}").json()["state"]["schedule_optimization"]["options"]}
    assert ids == current


def test_mysql_engine_uses_read_committed(monkeypatch):
    """Parallel plans deadlocked on MySQL (1213) under REPEATABLE READ gap locks taken by
    the agents' `DELETE ... WHERE plan_id = ?` before INSERT. No connection is opened here."""
    import importlib.util

    from app.core import config

    monkeypatch.setattr(config.settings, "database_url", "mysql+pymysql://u:p@localhost/x")
    spec = importlib.util.spec_from_file_location("_db_mysql_probe", Path(orchestrator.__file__).parent / "core" / "db.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.engine.dialect._on_connect_isolation_level == "READ COMMITTED"
    mod.engine.dispose()
