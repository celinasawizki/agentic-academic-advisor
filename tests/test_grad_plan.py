"""Graduation-plan upload: parsing the E-Graduation Plan grid, requiring it before schedules are
proposed, and scheduling only the courses the plan selects for the planning semester."""

import pytest
from fastapi.testclient import TestClient

from app.adapters.grad_plan import Frag, parse_grad_plan_pages
from app.core.config import settings
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def gate_on(monkeypatch):
    monkeypatch.setattr(settings, "require_grad_plan", True)


def grid_page() -> list[Frag]:
    """Positions modeled on Temple CLA's E-Graduation Plan: two semester columns per block, credits
    to the right of each course, a side panel on the right whose lines must not join a semester."""
    f = Frag
    return [
        f(232, 525, "E-Graduation Plan: Test Student (912345678)"), f(66, 500, "Major: Psychology"),
        # block 1: headings, column labels, a side-panel line that looks like a heading
        f(123, 477, "FALL 2026"), f(303, 477, " SPRING 2027"), f(496, 477, "Summer Courses"),
        f(134, 465.6, "Course"), f(225, 465.6, " Credits"), f(318, 465.6, " Course"), f(412, 465.6, " Credits"),
        f(487, 465.6, "   Course"),
        f(66, 454, "PSY 2201 (major)"), f(232, 454, " 4"), f(248, 454, " MKTG 2101 (minor prereq)"), f(420, 454, " 3"),
        f(444, 454, " Summer 2026?"),
        f(66, 442.8, "ENTR 2101 (minor)"), f(232, 442.8, " 3"), f(248, 442.8, " PSY 2601 (major) - ADD"), f(420, 442.8, " 3"),
        f(444, 442.8, " SGM Departmental Course (minor)"), f(577, 442.8, " 3"),
        f(248, 431, " GENED 0855 (GenEd GS) - WINTER BREAK"), f(420, 431, " 3"),
        f(66, 420, "TOTAL"), f(232, 420, " 7"), f(248, 420, " TOTAL"), f(420, 420, " 9"),
        # block 2
        f(123, 400, "FALL 2027"), f(289, 400, " SPRING 2028: GRAD"),
        f(134, 388.6, "Course"), f(318, 388.6, " Course"),
        f(66, 377, "PSY 2000-level BCS course (major) - 2104"), f(232, 377, " 3"),
        f(248, 377, " GenEd Science/Tech course (GS2) - is this needed? check with CLA"), f(420, 377, "3"),
        f(66, 366, "CIS 1068 (cert)"), f(232, 366, " 4"),
        # blank template block
        f(127, 340, "FALL 20"), f(307, 340, " SPRING 20"), f(134, 328.6, "Course"),
    ]


def test_parser_assigns_courses_to_their_semester_column():
    out = parse_grad_plan_pages([grid_page()], {"PSY 2201", "MKTG 2101"})
    terms = {t["term"]: t for t in out["terms"]}
    assert list(terms) == ["Fall 2026", "Spring 2027", "Fall 2027", "Spring 2028"]
    assert [(i["course"], i["credits"]) for i in terms["Fall 2026"]["items"]] == [("PSY 2201", 4), ("ENTR 2101", 3)]
    spring = terms["Spring 2027"]["items"]
    assert [(i["course"], i["credits"]) for i in spring] == [("MKTG 2101", 3), ("PSY 2601", 3), ("GENED 0855", 3)]
    assert "ADD" in spring[1]["notes"]
    # a winter-session course written in the spring column is not part of the spring schedule by default
    assert spring[2]["flags"] == ["winter_session"] and spring[2]["include"] is False
    assert terms["Spring 2027"]["planned_credits"] == 6
    # the side panel ("Summer 2026?", "SGM Departmental Course 3") joins no semester
    assert all("SGM" not in i["label"] for t in out["terms"] for i in t["items"])
    assert "Summer 2026" not in terms


def test_parser_keeps_requirement_slots_open_instead_of_guessing():
    terms = {t["term"]: t for t in parse_grad_plan_pages([grid_page()], set())["terms"]}
    slot = terms["Fall 2027"]["items"][0]
    assert slot["course"] is None and slot["include"] is False  # "PSY 2000-level" is not course PSY 2000
    assert slot["suggested_course"] == "PSY 2104"  # surfaced as a hint for the student, never scheduled on its own
    gened = terms["Spring 2028"]["items"][0]
    assert gened["course"] is None and "needs_confirmation" in gened["flags"]


def test_parser_drops_name_and_tuid_from_the_source_line():
    out = parse_grad_plan_pages([grid_page()], set())
    assert "912345678" not in (out["source"] or "") and "Test Student" not in (out["source"] or "")


def student_body(**kw):
    body = {"name": "Test", "academic_year": "Junior", "expected_graduation": "2028-05", "planning_term": "202703",
            "programs": ["PSY-BA", "GENED"], "credit_target": 12, "credit_min": 3, "credit_max": 18, "consent_to_process": True,
            "transcript": [{"course": c, "status": "completed", "grade": "A"} for c in ("PSY 1001", "PSY 2101", "CIS 1051")],
            "availability": []}
    body.update(kw)
    return body


SPRING = {"term": "Spring 2027", "items": [
    {"course": "MKTG 2101", "credits": 3}, {"course": "PSY 2601", "credits": 3}, {"course": "CIS 2109", "credits": 3},
    {"course": "GENED 0855", "credits": 3, "flags": ["winter_session"], "include": False},
]}
LATER = {"term": "Fall 2027", "items": [{"course": "PSY 3301", "credits": 3}]}


def test_onboarding_requires_a_grad_plan_with_the_planning_semester(client, gate_on):
    r = client.post("/api/students", json=student_body())
    assert r.status_code == 422 and "graduation plan" in r.json()["detail"]
    r = client.post("/api/students", json=student_body(grad_plan=[LATER]))
    assert r.status_code == 422 and "Spring 2027" in r.json()["detail"]
    empty = {"term": "Spring 2027", "items": [{"course": "GENED 0855", "include": False}, {"label": "GenEd GS slot"}]}
    assert client.post("/api/students", json=student_body(grad_plan=[empty])).status_code == 422


def test_no_schedule_is_proposed_for_a_real_student_without_a_grad_plan(client, monkeypatch):
    r = client.post("/api/students", json=student_body())  # created while the gate is off
    sid, auth = r.json()["id"], {"Authorization": f"Bearer {r.json()['access_token']}"}
    monkeypatch.setattr(settings, "require_grad_plan", True)
    r = client.post("/api/plans", json={"student_id": sid}, headers=auth)
    assert r.status_code == 422 and "graduation plan" in r.json()["detail"]
    # attaching a plan afterwards unblocks planning
    assert client.put(f"/api/students/{sid}/grad-plan", json={"terms": [SPRING]}, headers=auth).status_code == 200
    assert client.post("/api/plans", json={"student_id": sid}, headers=auth).status_code == 200


def test_grad_plan_cannot_be_written_to_a_shared_demo_student_or_someone_else(client, gate_on):
    assert client.put("/api/students/demo-lina/grad-plan", json={"terms": [SPRING]}).status_code == 400
    r = client.post("/api/students", json=student_body(grad_plan=[SPRING]))
    assert client.put(f"/api/students/{r.json()['id']}/grad-plan", json={"terms": [SPRING]}).status_code == 404


def run_plan_for(client, grad_plan):
    r = client.post("/api/students", json=student_body(grad_plan=grad_plan))
    assert r.status_code == 200, r.text
    auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.post("/api/plans", json={"student_id": r.json()["id"]}, headers=auth)
    assert r.status_code == 200, r.text
    plan = client.get(f"/api/plans/{r.json()['plan_id']}", headers=auth).json()
    assert plan["status"] == "complete", plan["state"].get("_error")
    return plan["state"]


def test_schedules_contain_exactly_the_grad_plan_courses_for_the_semester(client, gate_on):
    st = run_plan_for(client, [SPRING, LATER])
    opt = st["schedule_optimization"]
    assert opt["grad_plan_mode"] and opt["options"]
    for o in opt["options"]:
        # MKTG 2101 counts toward no PSY-BA requirement and is still scheduled; nothing else is added,
        # the winter-session course and the later semester's PSY 3301 are not scheduled
        assert {s["course"] for s in o["sections"]} == {"MKTG 2101", "PSY 2601", "CIS 2109"}
        assert all(s["from_grad_plan"] for s in o["sections"])
    assert len({tuple(sorted(s["id"] for s in o["sections"])) for o in opt["options"]}) == len(opt["options"])
    gp = st["course_discovery"]["grad_plan"]
    assert {c["course"] for c in gp["courses"]} == {"MKTG 2101", "PSY 2601", "CIS 2109"} and all(c["schedulable"] for c in gp["courses"])


def test_a_blocked_grad_plan_course_is_explained_not_replaced(client, gate_on):
    plan = {"term": "Spring 2027", "items": [{"course": "MKTG 2101", "credits": 3}, {"course": "PSY 3610", "credits": 3}]}
    st = run_plan_for(client, [plan])  # PSY 3610 needs PSY 2601, which the student hasn't taken
    gp = {c["course"]: c for c in st["course_discovery"]["grad_plan"]["courses"]}
    assert not gp["PSY 3610"]["schedulable"] and "Prerequisite" in gp["PSY 3610"]["reason"]
    opt = st["schedule_optimization"]
    assert not opt["options"]  # no substitute course is invented
    conflict = {g["description"] for i in opt["infeasible_strategies"] for g in i["conflict_set"]}
    assert "Include PSY 3610 (your graduation plan)" in conflict
    resolutions = [r for i in opt["infeasible_strategies"] for r in i["resolutions"]]
    defer = next(r for r in resolutions if r["relaxes"] == "req:PSY 3610")
    assert defer["feasible"] and defer["courses"] == ["MKTG 2101"]


def test_no_feasible_schedule_is_never_reported_as_satisfying_every_preference(client, gate_on):
    # QA on MySQL: with no soft preferences the ideal check short-circuited to "perfect", so the
    # student saw "We found a schedule that satisfies all of your preferences" next to zero options.
    plan = {"term": "Spring 2027", "items": [{"course": "MKTG 2101", "credits": 3}, {"course": "PSY 3610", "credits": 3}]}
    st = run_plan_for(client, [plan])
    assert not st["schedule_optimization"]["options"]
    ideal = st["schedule_optimization"]["ideal_analysis"]
    assert not ideal["perfect_exists"]
    assert "Include PSY 3610 (your graduation plan)" in {g["description"] for g in ideal["conflict_set"]}
    assert not st["student_explanation"]["headline"].startswith("We found a schedule")


def test_deferring_a_blocked_grad_plan_course_schedules_the_rest(client, gate_on):
    plan = {"term": "Spring 2027", "items": [{"course": "MKTG 2101", "credits": 3}, {"course": "PSY 3610", "credits": 3}]}
    r = client.post("/api/students", json=student_body(grad_plan=[plan]))
    auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
    pid = client.post("/api/plans", json={"student_id": r.json()["id"]}, headers=auth).json()["plan_id"]
    assert client.post(f"/api/plans/{pid}/resolve", json={"relaxes": "req:PSY 3610"}, headers=auth).status_code == 200
    opt = client.get(f"/api/plans/{pid}", headers=auth).json()["state"]["schedule_optimization"]
    assert opt["options"] and all({s["course"] for s in o["sections"]} == {"MKTG 2101"} for o in opt["options"])


def test_two_blocked_grad_plan_courses_get_a_verified_combined_deferral(client, gate_on):
    # QA: with two blocked planned courses, deferring either one alone is infeasible and no other
    # resolution worked, so the student had no way forward.
    plan = {"term": "Spring 2027", "items": [{"course": "MKTG 2101", "credits": 3}, {"course": "PSY 3610", "credits": 3},
                                             {"course": "PSY 3710", "credits": 3}]}
    r = client.post("/api/students", json=student_body(grad_plan=[plan]))
    auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
    pid = client.post("/api/plans", json={"student_id": r.json()["id"]}, headers=auth).json()["plan_id"]
    opt = client.get(f"/api/plans/{pid}", headers=auth).json()["state"]["schedule_optimization"]
    assert not opt["options"]
    resolutions = opt["infeasible_strategies"][0]["resolutions"]
    singles = [x for x in resolutions if " + " not in x["relaxes"]]
    assert singles and not any(x["feasible"] for x in singles)  # each planned course is its own conflict
    combo = next(x for x in resolutions if set(x["relaxes"].split(" + ")) == {"req:PSY 3610", "req:PSY 3710"})
    assert combo["feasible"] and set(combo["courses"]) == {"MKTG 2101"} and combo["type"] == "defer_course"
    assert client.post(f"/api/plans/{pid}/resolve", json={"relaxes": combo["relaxes"]}, headers=auth).status_code == 200
    opt = client.get(f"/api/plans/{pid}", headers=auth).json()["state"]["schedule_optimization"]
    assert opt["options"] and all({s["course"] for s in o["sections"]} == {"MKTG 2101"} for o in opt["options"])


def test_combined_resolution_only_combines_course_deferrals(client, gate_on):
    plan = {"term": "Spring 2027", "items": [{"course": "MKTG 2101", "credits": 3}]}
    r = client.post("/api/students", json=student_body(grad_plan=[plan]))
    auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
    pid = client.post("/api/plans", json={"student_id": r.json()["id"]}, headers=auth).json()["plan_id"]
    bad = client.post(f"/api/plans/{pid}/resolve", json={"relaxes": "req:MKTG 2101 + f1:full_time"}, headers=auth)
    assert bad.status_code == 422


def test_show_different_options_varies_sections_not_courses(client, gate_on):
    r = client.post("/api/students", json=student_body(grad_plan=[SPRING]))
    auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
    pid = client.post("/api/plans", json={"student_id": r.json()["id"]}, headers=auth).json()["plan_id"]
    before = client.get(f"/api/plans/{pid}", headers=auth).json()["state"]["schedule_optimization"]["options"]
    assert client.post(f"/api/plans/{pid}/regenerate", headers=auth).status_code == 200
    after = client.get(f"/api/plans/{pid}", headers=auth).json()["state"]["schedule_optimization"]["options"]
    seen = {tuple(sorted(s["id"] for s in o["sections"])) for o in before}
    for o in after:
        assert {s["course"] for s in o["sections"]} == {"MKTG 2101", "PSY 2601", "CIS 2109"}
        assert tuple(sorted(s["id"] for s in o["sections"])) not in seen


def test_a_full_grad_plan_course_stays_schedulable_with_a_seat_warning():
    from helpers import course, section

    from app.agents.discovery import evaluate_course
    from app.domain import StudentProfile
    stu = StudentProfile(id="s", name="s", academic_year="Junior", expected_graduation="2028-05", catalog_year=None,
                         planning_term="202703", program_ids=[], campus="Main", f1_status="no", interests_text="",
                         transcript=[], availability=[])
    full = section("202703-PSY2401-001", "PSY 2401", [("MW", "09:30", "10:45")]).model_copy(update={"seats_available": 0})
    japan = section("202703-PSY2401-801", "PSY 2401", [("TR", "12:00", "13:30")], campus="Japan")
    c = course("PSY 2401")
    assert evaluate_course(c, [full, japan], stu, set(), "Spring 2027")["reason"] == "No open Main Campus or online section"
    ev = evaluate_course(c, [full, japan], stu, set(), "Spring 2027", allow_full=True)
    assert ev["reason"] is None and [e["section"]["id"] for e in ev["eligible"]] == ["202703-PSY2401-001"]
    assert ev["eligible"][0]["seats_full"] and any("waitlist" in n["reason"] for n in ev["notes"])
