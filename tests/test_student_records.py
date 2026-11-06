"""Student-record writes must fit the schema on strict servers (MySQL), where an over-long value is a
500 error, not a silent truncation as on SQLite; and onboarding must reject what it can't plan for."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import AvailabilityBlock, Student, TranscriptEntry
from app.routers.students import AvailabilityIn, OnboardingIn, TranscriptIn


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def body(**kw):
    b = {"name": "T", "academic_year": "Junior", "expected_graduation": "2028-05", "planning_term": "202703",
         "programs": ["PSY-BA", "GENED"], "credit_target": 12, "credit_min": 3, "credit_max": 18, "consent_to_process": True,
         "transcript": [{"course": "PSY 1001", "status": "completed", "grade": "A"}]}
    b.update(kw)
    return b


def _max_length(model, field):
    return next(m.max_length for m in model.model_fields[field].metadata if hasattr(m, "max_length"))


def test_onboarding_limits_fit_the_columns_they_are_stored_in():
    cols = Student.__table__.c
    for field, col in (("name", cols.name), ("academic_year", cols.academic_year), ("catalog_year", cols.catalog_year)):
        assert _max_length(OnboardingIn, field) <= col.type.length, field
    assert _max_length(AvailabilityIn, "label") <= AvailabilityBlock.__table__.c.label.type.length
    assert _max_length(TranscriptIn, "grade") <= TranscriptEntry.__table__.c.grade.type.length
    assert _max_length(TranscriptIn, "term") <= TranscriptEntry.__table__.c.term.type.length


def test_unknown_program_is_rejected_at_onboarding(client):
    r = client.post("/api/students", json=body(programs=["PSY-BA", "not-a-real-program"]))
    assert r.status_code == 422 and "not-a-real-program" in r.json()["detail"]
    assert client.post("/api/students", json=body(programs=["x" * 500])).status_code == 422


def test_persisted_availability_label_fits_its_column(client):
    """LLM-parsed change requests carry unbounded labels; persisting one to the student's record must
    not exceed availability_blocks.label (VARCHAR(80) on MySQL)."""
    from app.core.db import SessionLocal
    from app.domain import AvailBlock, StudentProfile
    from app.models import PlanRun
    from app.routers.plans import persist_student

    r = client.post("/api/students", json=body())
    sid, auth = r.json()["id"], {"Authorization": f"Bearer {r.json()['access_token']}"}
    pid = client.post("/api/plans", json={"student_id": sid}, headers=auth).json()["plan_id"]
    db = SessionLocal()
    try:
        plan = db.get(PlanRun, pid)
        student = StudentProfile(**plan.state["_student"])
        student.availability = [AvailBlock(day="M", start="09:00", end="10:00", kind="hard", label="L" * 300)]
        persist_student(db, plan, student)
        db.commit()
        labels = [b.label for b in db.query(AvailabilityBlock).filter_by(student_id=sid).all()]
        assert labels and all(len(x) <= AvailabilityBlock.__table__.c.label.type.length for x in labels)
    finally:
        db.close()
