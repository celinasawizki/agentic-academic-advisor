"""Query shapes that must work on MySQL (strict, small sort buffer, remote round trips), not only SQLite."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.core.db import SessionLocal, engine
from app.main import app
from app.models import PlanRun


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


class _Statements:
    def __init__(self):
        self.sql: list[str] = []

    def __call__(self, conn, cursor, statement, *args):
        self.sql.append(statement)

    def __enter__(self):
        event.listen(engine, "before_cursor_execute", self)
        return self

    def __exit__(self, *exc):
        event.remove(engine, "before_cursor_execute", self)


def test_advisor_overview_picks_newest_plan_without_sorting_plan_state(client):
    """Bug: ORDER BY created_at over whole plan_runs rows put the ~1 MB `state` JSON in MySQL's
    sort buffer -> 500 "Out of sort memory" (1038) on the advisor view."""
    big = {"_filler": "x" * 300_000}  # larger than MySQL's default 256 KB sort buffer
    base = datetime(2099, 1, 1, tzinfo=timezone.utc)  # newer than any plan another test made
    ids = ["plan-qa-sort-old", "plan-qa-sort-new"]
    with SessionLocal() as db:
        for i, pid in enumerate(ids):
            db.add(PlanRun(id=pid, student_id="demo-marcus", term_id="202703", status="complete",
                           state={**big, "student_explanation": {"headline": pid}}, created_at=base + timedelta(days=i)))
        db.commit()
    try:
        with _Statements() as st:
            r = client.get("/api/advisor/overview", headers={"X-Demo-Role": "advisor"})
        assert r.status_code == 200
        marcus = next(x for x in r.json() if x["student_id"] == "demo-marcus")
        assert marcus["plan_id"] == "plan-qa-sort-new" and marcus["explanation"] == "plan-qa-sort-new"
        for sql in st.sql:
            if "ORDER BY" in sql and "plan_runs" in sql:
                assert "plan_runs.state" not in sql, sql
    finally:
        with SessionLocal() as db:
            db.query(PlanRun).filter(PlanRun.id.in_(ids)).delete(synchronize_session=False)
            db.commit()


def test_program_list_loads_sources_in_bulk(client):
    """Bug: one lazy source query per program (~435 round trips, ~10 s on the remote MySQL)."""
    with _Statements() as st:
        r = client.get("/api/catalog/programs")
    assert r.status_code == 200 and r.json()
    assert len(st.sql) <= 3, st.sql


def test_list_endpoints_have_a_deterministic_order(client):
    """SQLite returns insertion order and MySQL primary-key order unless the query sorts."""
    demo = [s["id"] for s in client.get("/api/students/demo").json()]
    assert demo == sorted(demo)
    terms = [t["id"] for t in client.get("/api/catalog/terms").json()]
    assert terms == sorted(terms)


def test_program_ids_must_match_exactly(client):
    """MySQL's case-insensitive collation finds "psy-ba" for "PSY-BA"; the student would then be stored
    with an id the requirements lookup never matches and the plan would run with no requirements."""
    r = client.post("/api/students", json={"name": "T", "academic_year": "Junior", "expected_graduation": "2028-05",
                                           "planning_term": "202703", "programs": ["psy-ba"], "credit_target": 12,
                                           "credit_min": 3, "credit_max": 18, "consent_to_process": True})
    assert r.status_code == 422 and "psy-ba" in r.json()["detail"]
