"""Regression tests for the audit findings and the features added with them."""

import pytest
from fastapi.testclient import TestClient
from helpers import block, course, section

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def plan_for(client, student_id="demo-lina", headers=None):
    r = client.post("/api/plans", json={"student_id": student_id}, headers=headers or {})
    assert r.status_code == 200, r.text
    plan = client.get(f"/api/plans/{r.json()['plan_id']}", headers=headers or {}).json()
    assert plan["status"] == "complete", plan["state"].get("_error")
    return plan


def real_student(client, programs, transcript, interests="", availability=None, credits=(12, 3, 18)):
    r = client.post("/api/students", json={
        "name": "Test", "academic_year": "Junior", "expected_graduation": "2028-05", "planning_term": "202703", "programs": programs,
        "credit_target": credits[0], "credit_min": credits[1], "credit_max": credits[2], "consent_to_process": True,
        "interests_text": interests, "transcript": transcript, "availability": availability or []})
    assert r.status_code == 200, r.text
    return r.json()["id"], {"Authorization": f"Bearer {r.json()['access_token']}"}


# --- conflict resolution ----------------------------------------------------

def test_accepting_a_soft_tradeoff_regenerates_without_that_preference(client):
    plan = plan_for(client)
    ideal = plan["state"]["schedule_optimization"]["ideal_analysis"]
    assert not ideal["perfect_exists"]
    soft = next(r for r in ideal["resolutions"] if r["type"] == "relax_soft")
    r = client.post(f"/api/plans/{plan['id']}/resolve", json={"relaxes": soft["relaxes"]})
    assert r.status_code == 200
    after = client.get(f"/api/plans/{plan['id']}").json()
    st = after["state"]
    assert after["iteration"] == 2
    assert "Prefer Fridays off" in st["_student"]["preferences"]["accepted_tradeoffs"]
    assert all(b["label"] != "Prefer Fridays off" for b in st["_student"]["availability"])
    assert st["schedule_optimization"]["ideal_analysis"]["perfect_exists"]


def test_hard_availability_and_f1_are_never_relaxed_by_resolve(client):
    plan = plan_for(client)
    assert client.post(f"/api/plans/{plan['id']}/resolve", json={"relaxes": "avail:Work (campus job)"}).status_code == 422
    assert client.post(f"/api/plans/{plan['id']}/resolve", json={"relaxes": "f1"}).status_code == 422


def test_deferring_a_critical_course_removes_it_from_required_set(client):
    plan = plan_for(client)
    r = client.post(f"/api/plans/{plan['id']}/resolve", json={"relaxes": "must:PSY 2201"})
    assert r.status_code == 200
    st = client.get(f"/api/plans/{plan['id']}").json()["state"]
    assert "PSY 2201" not in st["scheduling_constraints"]["must_courses_graduation_strategy"]
    assert any(p["issue"] == "deferred_by_student" for p in st["scheduling_constraints"]["pre_checks"])
    assert not st["schedule_optimization"]["infeasible_strategies"]


def test_regenerate_produces_different_combinations(client):
    plan = plan_for(client)
    before = {frozenset(s["course"] for s in o["sections"]) for o in plan["state"]["schedule_optimization"]["options"]}
    assert client.post(f"/api/plans/{plan['id']}/regenerate").status_code == 200
    after_opts = client.get(f"/api/plans/{plan['id']}").json()["state"]["schedule_optimization"]["options"]
    after = {frozenset(s["course"] for s in o["sections"]) for o in after_opts}
    assert after and not (after & before)


def test_tuesday_job_request_updates_constraints_without_restarting(client):
    plan = plan_for(client)
    r = client.post(f"/api/plans/{plan['id']}/modify", json={"message": "I just got a job on Tuesdays from 1 PM to 6 PM. Find another schedule."})
    assert r.json()["applied"] == ["Added hard block: Job T 13:00-18:00"]
    st = client.get(f"/api/plans/{plan['id']}").json()["state"]
    for o in st["schedule_optimization"]["options"]:
        for s in o["sections"]:
            for m in s["meetings"]:
                if "T" in m["days"]:
                    assert m["end"] <= "13:00" or m["start"] >= "18:00"


# --- requirement reliability -------------------------------------------------

def test_requirement_reliability_statuses(client):
    sid, auth = real_student(client, ["PSY-BA", "GENED"], [{"course": "PSY 1001", "status": "completed", "grade": "A"}])
    st = plan_for(client, sid, auth)["state"]
    rel = {r["id"]: r["reliability"] for r in st["degree_requirements"]["requirements"]}
    assert rel["PSY-R2-PSY2101"] == "UNAVAILABLE"  # no PSY 2101 section in the fixture term
    assert rel["PSY-R5"] == "BLOCKED"  # capstone offered, but prerequisite PSY 2201 missing
    assert "VERIFIED" not in rel.values()  # nothing is verified without a human record
    counts = st["degree_requirements"]["reliability_counts"]
    assert counts["UNAVAILABLE"] >= 1 and counts["BLOCKED"] >= 1


def test_free_text_rules_are_ambiguous():
    from app.agents.requirements import reliability
    base = {"id": "x", "kind": "count", "verification_status": "parsed"}
    assert reliability({**base, "kind": "manual"}, {}, False, False)[0] == "AMBIGUOUS"
    assert reliability({**base, "verification_status": "needs_review"}, {}, False, False)[0] == "AMBIGUOUS"
    assert reliability(base, {}, True, False)[0] == "AMBIGUOUS"  # catalog-year mismatch
    assert reliability(base, {}, False, False)[0] == "PENDING_VERIFICATION"
    assert reliability(base, {"x": {"verified_by": "Advisor A", "evidence": "degree audit"}}, False, False)[0] == "VERIFIED"


# --- interest-based electives ----------------------------------------------

def test_interest_electives_are_never_presented_as_requirements(client):
    sid, auth = real_student(client, ["GENED"],
                             [{"course": "PSY 1001", "status": "completed", "grade": "A"}, {"course": "PSY 2101", "status": "completed", "grade": "B"}],
                             interests="Industrial-organizational psychology, leadership and work motivation")
    st = plan_for(client, sid, auth)["state"]
    electives = {e["course"] for e in st["interest_matching"]["interest_electives"]}
    assert "PSY 3301" in electives
    for o in st["student_explanation"]["options"]:
        for c in o["courses"]:
            if c["course"] in electives:
                assert c["category"] == "INTEREST_ELECTIVE"
                assert c["requirement_status"] == "Not a degree requirement"
                assert not any(r["kind"] == "requirement" and r.get("status") not in ("not_a_requirement",) for r in c["reasons"])


def test_classify_courses():
    from app.agents.categories import classify
    state = {"degree_requirements": {"remaining": [
        {"id": "R1", "kind": "count", "options": [["PSY 3096"]], "patterns": []},
        {"id": "R2", "kind": "count", "options": [["PSY 3301"], ["PSY 3418"]], "patterns": []}]}}
    assert classify("PSY 3096", ["R1"], state) == "REQUIRED"
    assert classify("PSY 3301", ["R2"], state) == "DEGREE_ELECTIVE"
    assert classify("CIS 3203", ["FREE_ELECTIVE"], state) == "INTEREST_ELECTIVE"


# --- explanations, decisions, provenance -------------------------------------

def test_every_agent_records_a_structured_decision(client):
    plan = plan_for(client)
    done = [a for a in plan["agents"] if a["status"] == "complete"]
    assert len(done) == 9
    for a in done:
        d = a["decision"]
        assert d["task"] and isinstance(d["findings"], list) and d["validation"]["status"] in ("passed", "warnings", "failed", "n/a")


def test_course_explanations_include_alternatives_unverified_and_provenance(client):
    st = plan_for(client)["state"]
    c = st["student_explanation"]["options"][0]["courses"][0]
    for key in ("category", "alternatives_considered", "unverified", "prerequisites", "section_choice"):
        assert key in c
    d = c["data"]
    assert d["term"] == "Spring 2027" and d["crn"] and d["campus"] and d["retrieved_at"] and "seats" in d
    assert st["student_explanation"]["headline"].startswith("We couldn't find a 15-credit schedule")


def test_missing_course_data_is_reported(client):
    sid, auth = real_student(client, ["PSY-BA"], [{"course": "ZZZ 1001", "status": "completed", "grade": "A"}])
    st = plan_for(client, sid, auth)["state"]
    assert any("ZZZ 1001" in w for w in st["academic_profile"]["warnings"])


# --- section components in review ------------------------------------------

def test_review_flags_missing_and_inferred_components():
    from app.agents.base import Catalog, PlanContext
    from app.agents.review import review_sections
    from app.domain import PlanningPreferences, StudentProfile
    lec = section("lec", "PHYS 1021", [("MW", "10:00", "10:50")])
    lab = section("lab", "PHYS 1021", [("R", "09:00", "10:50")]).model_copy(update={"component": "Lab"})
    student = StudentProfile(id="s", name="s", academic_year="Junior", expected_graduation="2028-05", catalog_year=None,
                             planning_term="202703", program_ids=[], campus="Main", f1_status="no", interests_text="",
                             transcript=[], availability=[block("F", "07:00", "22:00")],
                             preferences=PlanningPreferences(credit_min=3, credit_max=18, credit_target=12))
    cat = Catalog(term_id="202703", term_name="Spring 2027", courses={"PHYS 1021": course("PHYS 1021", 4)}, sections=[lec, lab],
                  requirements=[], programs={}, double_count_allowed=set())
    ctx = PlanContext(db=None, plan_id="p", student=student, catalog=cat, state={"degree_requirements": {"requirements": []}})
    comps = {"PHYS 1021": {"primary", "Lab"}}
    only_lecture = {c["check"]: c for c in review_sections(ctx, [lec], {"PHYS 1021": ["R"]}, comps)}
    assert not only_lecture["component_missing:PHYS 1021"]["passed"]
    both = {c["check"]: c for c in review_sections(ctx, [lec, lab], {"PHYS 1021": ["R"]}, comps)}
    assert "component_missing:PHYS 1021" not in both and not both["component_pairing:PHYS 1021"]["passed"]
    assert "4 credits" in both["credit_range"]["detail"]
