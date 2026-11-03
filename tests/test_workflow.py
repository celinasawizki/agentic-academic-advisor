"""Integration test of the main planning workflow through the HTTP API."""

import io

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def run_plan(client, student_id="demo-lina"):
    r = client.post("/api/plans", json={"student_id": student_id})
    assert r.status_code == 200
    plan = client.get(f"/api/plans/{r.json()['plan_id']}").json()
    assert plan["status"] == "complete", plan["state"].get("_error")
    return plan


def test_demo_plan_end_to_end(client):
    plan = run_plan(client)
    st = plan["state"]
    executed = [a["agent"] for a in plan["agents"] if a["status"] == "complete"]
    assert executed[:9] == ["academic_profile", "degree_requirements", "course_discovery", "interest_matching",
                            "graduation_planning", "scheduling_constraints", "schedule_optimization", "academic_review",
                            "student_explanation"]
    opts = st["schedule_optimization"]["options"]
    assert 1 <= len(opts) <= 3
    for o in opts:
        assert st["academic_review"]["reviews"][o["id"]]["status"] != "rejected"
        assert all(s["campus"] in ("Main", "Online") for s in o["sections"])
        assert all(s["data_source"] == "demo_fixture" for s in o["sections"])
    # Work hours (hard) are never violated.
    for o in opts:
        for s in o["sections"]:
            for m in s["meetings"]:
                if "M" in m["days"] or "W" in m["days"]:
                    assert m["end"] <= "13:00" or m["start"] >= "18:00"
    # PSY 2201 is only compatible on Friday: no perfect schedule exists, and it's explained.
    ideal = st["schedule_optimization"]["ideal_analysis"]
    assert ideal["perfect_exists"] is False
    assert any("PSY 2201" in g["description"] for g in ideal["conflict_set"])
    assert st["student_explanation"]["headline"].startswith("We couldn't find")
    # Prerequisite-blocked interest course is surfaced with alternatives.
    assert any(b["course"] == "PSY 4996" for b in st["student_explanation"]["blocked_interest_alternatives"])


def test_natural_language_change_reruns_agents(client):
    plan = run_plan(client)
    r = client.post(f"/api/plans/{plan['id']}/modify", json={"message": "Give me Fridays off"})
    body = r.json()
    assert body["rerun"] and any("HARD" in a for a in body["applied"])
    after = client.get(f"/api/plans/{plan['id']}").json()
    assert after["status"] == "complete" and after["iteration"] == 2
    st = after["state"]
    for o in st["schedule_optimization"]["options"]:
        assert all("F" not in m["days"] for s in o["sections"] for m in s["meetings"])
    # Graduation strategy cannot keep PSY 2201 with Fridays hard-blocked -> infeasible with explanation.
    infeasible = st["schedule_optimization"]["infeasible_strategies"]
    assert infeasible and infeasible[0]["strategy"] == "graduation"
    kinds = {res["type"] for res in infeasible[0]["resolutions"]}
    assert "defer_course" in kinds


def test_credit_change(client):
    plan = run_plan(client)
    client.post(f"/api/plans/{plan['id']}/modify", json={"message": "I want to take 18 credits instead"})
    st = client.get(f"/api/plans/{plan['id']}").json()["state"]
    assert st["_student"]["preferences"]["credit_target"] == 18


def test_manual_validation_detects_conflict(client):
    plan = run_plan(client)
    r = client.post(f"/api/plans/{plan['id']}/validate",
                    json={"section_ids": ["202703-PSY3301-001", "202703-PSY2201-001"]})
    body = r.json()
    assert not body["valid"]
    assert any(c["check"] == "hard_availability" and not c["passed"] for c in body["checks"])


def test_mock_tuportal_export(client):
    plan = run_plan(client)
    opt = plan["state"]["schedule_optimization"]["options"][0]
    r = client.post("/api/integration/tuportal/drafts", json={"plan_id": plan["id"], "option_id": opt["id"]})
    body = r.json()
    assert body["mock"] is True and body["draft"]["registered"] is False
    assert body["draft"]["draft_id"].startswith("MOCK-DRAFT-")


def test_advisor_requires_role(client):
    assert client.get("/api/advisor/overview").status_code == 403
    r = client.get("/api/advisor/overview", headers={"X-Demo-Role": "advisor"})
    assert r.status_code == 200 and any(s["student_id"] == "demo-lina" for s in r.json())


def test_upload_validation(client):
    r = client.post("/api/degree-audit/parse", files={"file": ("x.pdf", b"not a pdf", "application/pdf")})
    assert r.status_code == 415
    buf = io.BytesIO()
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    w.write(buf)
    r = client.post("/api/degree-audit/parse", files={"file": ("a.pdf", buf.getvalue(), "application/pdf")})
    assert r.status_code == 200 and r.json()["entries"] == []


def test_onboarding_requires_consent_and_supported_campus(client):
    base = {"name": "Test", "academic_year": "Junior", "expected_graduation": "2028-05", "planning_term": "202703",
            "programs": ["PSY-BA"], "credit_target": 15, "credit_min": 12, "credit_max": 18, "consent_to_process": False}
    assert client.post("/api/students", json=base).status_code == 400
    assert client.post("/api/students", json={**base, "consent_to_process": True, "campus": "Rome"}).status_code == 422
    r = client.post("/api/students", json={**base, "consent_to_process": True,
                                           "transcript": [{"course": "PSY 1001", "status": "completed", "grade": "A"}]})
    sid = r.json()["id"]
    plan = run_plan(client, sid)
    # Only 6 eligible credits exist for this student, so 12+ is infeasible and must be explained, not faked.
    opt = plan["state"]["schedule_optimization"]
    assert opt["options"] == []
    for inf in opt["infeasible_strategies"]:
        assert any(g["kind"] == "credit_min" for g in inf["conflict_set"])
        assert any(r["type"] == "reduce_credits" and r["feasible"] for r in inf["resolutions"])
    assert client.delete(f"/api/students/{sid}").status_code == 200
    assert client.get(f"/api/students/{sid}").status_code == 404


def test_parse_audit_text():
    from app.adapters.degree_audit import parse_audit_text
    text = "PSY 1001 Intro to Psychology FA 2025 A\nCIS 1068 Program Design IP\nGENED 0812 Creative Acts TR"
    rows = {e["course"]: e for e in parse_audit_text(text, {"PSY 1001", "CIS 1068"})["entries"]}
    assert rows["PSY 1001"]["status"] == "completed"
    assert rows["CIS 1068"]["status"] == "in_progress"
    assert rows["GENED 0812"]["status"] == "transfer"
