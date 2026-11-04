"""School/college and university requirement layers, the Requirements Research Agent,
and real-data coverage for every Temple program."""

import json
from pathlib import Path

import pytest
from helpers import course, prefs, req, section

from app.domain import CourseData, TranscriptItem
from app.ingest.school import applies, build_layers, language_subjects, summary_facts
from app.optimizer import STRATEGIES, Candidate, ScheduleModel
from app.rules import requirement_progress

REAL = Path(__file__).resolve().parents[1] / "data" / "temple"
PAGE = """<div id="requirementstextcontainer"><h2>Summary of Requirements</h2>
<ol><li class="bold">University Requirements <ul><li>Students must complete all University requirements.</li>
<li>All undergraduate students must complete at least two writing-&#8203;intensive (WI) courses. The specific course options are:
<table class="sc_courselist"><tr><td class="codecol"><a>PSY 3096</a></td></tr><tr><td class="codecol"><a>PSY 4696</a></td></tr></table></li></ul></li></ol>
<p>Completion of a minimum of 123 credits, including 90 credits in CLA/CST courses.</p>
<p>Minimum grades of C- are required in prerequisite courses.</p>
<p>A minimum grade of C in each course is required.</p>
<table class="sc_courselist"><tr><td class="codecol"><a>PSY 1001</a></td></tr></table></div>
<div id="academicplantextcontainer"></div>"""
SCHOOL = """<div id="collegerequirementstextcontainer"><h2>Professional Development Requirement</h2>
<p>All students in the College are required to take a 1 credit seminar in professional development.</p>
<p>The minimum acceptable grade in a course taken to fulfill major requirements is a "C-".</p></div><div id="advisingtextcontainer"></div>"""
SPEC = {"_meta": {"catalog_year": "2026-2027"}, "layers": [
    {"id": "u", "name": "University", "college": None, "url": "https://bulletin.temple.edu/u/", "applies": {"types": ["major"]},
     "rules": [{"id": "res", "name": "Residency", "kind": "milestone", "metric": "temple_credits", "needed": 30, "evidence": "30 credits at Temple"}]},
    {"id": "cla", "name": "CLA", "college": "liberal-arts", "url": "https://bulletin.temple.edu/undergraduate/liberal-arts/",
     "container": "collegerequirementstextcontainer", "applies": {"types": ["major"]},
     "min_grade": {"grade": "C-", "evidence": "The minimum acceptable grade in a course taken to fulfill major requirements is a \"C-\""},
     "rules": [{"id": "pd", "name": "PD seminar", "kind": "count", "needed": 1, "options": [["CLA 1002"], ["PSY 1002"]],
                "evidence": "required to take a 1 credit seminar in professional development."},
               {"id": "lang", "name": "Language", "kind": "count", "needed": 1, "language_level": 1002, "applies": {"degrees": ["ba"]},
                "evidence": "This sentence is not on the page."}]}]}
PROGRAMS = [
    {"id": "psychology-ba", "name": "Psychology BA", "type": "major", "college": "College of Liberal Arts",
     "source_url": "https://bulletin.temple.edu/undergraduate/liberal-arts/psychology-ba/"},
    {"id": "neuroscience-bs", "name": "Neuroscience BS", "type": "major", "college": "College of Liberal Arts",
     "source_url": "https://bulletin.temple.edu/undergraduate/liberal-arts/neuroscience-bs/"},
    {"id": "psychology-minor", "name": "Psychology Minor", "type": "minor", "college": "College of Liberal Arts",
     "source_url": "https://bulletin.temple.edu/undergraduate/liberal-arts/psychology-minor/"},
]
COURSES = {"SPAN 1001": CourseData(code="SPAN 1001", title="Basic I", credits=4, description="Grammar and conversation."),
           "SPAN 1002": CourseData(code="SPAN 1002", title="Basic II", credits=4, description="Continued speaking practice."),
           "MATH 1001": CourseData(code="MATH 1001", title="Algebra", credits=3, description="Functions."),
           "MATH 1002": CourseData(code="MATH 1002", title="Algebra II", credits=3, description="More functions.")}


def pages(url):
    return {"https://bulletin.temple.edu/undergraduate/liberal-arts/": SCHOOL}.get(url, PAGE if "psychology" in url or "neuro" in url else None)


def test_summary_facts_reads_wi_courses_credits_and_min_grade():
    f = summary_facts(PAGE)
    assert f["writing_intensive"]["codes"] == ["PSY 3096", "PSY 4696"]  # table nested in the list item, zero-width space removed
    assert f["total_credits"]["needed"] == 123
    assert f["min_grade"]["grade"] == "C"  # the prerequisite sentence is not a program grade rule


def test_layers_apply_by_program_type_and_degree():
    out = build_layers(SPEC, PROGRAMS, COURSES, pages)
    assert out["links"]["psychology-ba"] == ["layer-u", "layer-cla--lang", "psychology-ba--degree"]
    assert out["links"]["neuroscience-bs"][:2] == ["layer-u", "layer-cla"]  # the BA-only language rule does not apply to a BS
    assert out["links"]["psychology-minor"] == []  # school graduation rules are not applied to minors
    ba = next(l for l in out["layers"] if l["id"] == "layer-cla--lang")
    lang = next(r for r in ba["requirements"] if r["id"].endswith("-lang"))
    assert lang["options"] == [["SPAN 1002"]]  # derived from course descriptions, not MATH
    assert lang["verification_status"] == "needs_review" and not lang["evidence_found"]  # quote missing from the page
    pd = next(r for r in ba["requirements"] if r["id"].endswith("-pd"))
    assert pd["evidence_found"] and pd["verification_status"] == "parsed"
    assert out["min_grades"]["psychology-ba"]["grade"] == "C"  # the program page overrides its school's default


def test_applies_conditions():
    p = {"id": "music-education-bm", "name": "Music Education BM", "type": "major"}
    assert applies({"types": ["major"], "name_excludes": "Dance"}, p)
    assert not applies({"degrees": ["ba"]}, p)
    assert not applies({"name_matches": "Technology"}, p)


def test_language_subjects_exclude_asl_unless_allowed():
    cs = {**COURSES, "CSCD 1001": CourseData(code="CSCD 1001", title="American Sign Language I", credits=3, description="Vocabulary"),
          "CSCD 1002": CourseData(code="CSCD 1002", title="American Sign Language II", credits=3, description="Grammar")}
    assert language_subjects(cs) == ["SPAN"]
    assert language_subjects(cs, include_asl=True) == ["CSCD", "SPAN"]


def test_school_layer_double_counts_with_the_major_but_not_within_itself():
    rules = [req("MAJ", ["PSY 1002"]), req("PD", ["PSY 1002", "CLA 1002"], program="L", ptype="school"),
             req("GG1", patterns=[{"attribute": "GG"}], program="L", ptype="school"),
             req("GG2", patterns=[{"attribute": "GG"}], program="L", ptype="school")]
    courses = {"PSY 1002": course("PSY 1002", 1), "ANTH 0827": CourseData(code="ANTH 0827", title="x", credits=3, description="", attributes=["GG"])}
    t = [TranscriptItem(course="PSY 1002", status="completed", grade="A"), TranscriptItem(course="ANTH 0827", status="completed", grade="B")]
    out = {p.requirement.id: p for p in requirement_progress(rules, t, set(), courses)}
    assert out["MAJ"].status == "complete" and out["PD"].status == "complete"  # same course, degree-level rule
    assert out["GG1"].status == "complete" and out["GG2"].status == "incomplete"  # a second GG course is still needed
    assert [p.requirement.id for p in requirement_progress(rules, t, set(), courses)] == ["MAJ", "PD", "GG1", "GG2"]  # bulletin order kept


def test_milestones_credits_residency_gpa_and_wi():
    m = lambda rid, metric, n, options=None: req(rid, kind="milestone", n=n, program="L", ptype="university",  # noqa: E731
                                                  patterns=[{"metric": metric}], options=options or [])
    rules = [m("TOT", "total_credits", 9), m("UP", "upper_level_credits", 3), m("RES", "temple_credits", 6), m("GPA", "gpa", 3.0),
             m("WI", "wi_courses", 2, [["PSY 3096"], ["PSY 4696"]])]
    courses = {c: course(c) for c in ("PSY 1001", "PSY 3096", "ENG 0802", "PSY 4696")}
    t = [TranscriptItem(course="PSY 1001", status="completed", grade="A"), TranscriptItem(course="PSY 3096", status="completed", grade="C"),
         TranscriptItem(course="ENG 0802", status="transfer", grade="TR"), TranscriptItem(course="PSY 4696", status="in_progress")]
    out = {p.requirement.id: p for p in requirement_progress(rules, t, set(), courses)}
    assert out["TOT"].value == 9 and out["TOT"].status == "complete"
    assert out["UP"].value == 3 and out["UP"].status == "complete"
    assert out["RES"].value == 6  # the transfer course doesn't count toward residency
    assert out["GPA"].value == 3.0 and out["GPA"].status == "complete"
    assert out["WI"].value == 1 and out["WI"].status == "in_progress"
    assert all(p.remaining_courses == 0 for p in out.values())  # milestones never create schedule slots


def test_program_minimum_grade_is_enforced():
    r = req("R", ["PSY 2101"]).model_copy(update={"min_grade": "C-"})
    t = [TranscriptItem(course="PSY 2101", status="completed", grade="D+")]
    p = requirement_progress([r], t, set(), {"PSY 2101": course("PSY 2101")})[0]
    assert p.status == "incomplete" and "below this program's minimum (C-)" in p.notes[0]


def test_course_and_its_unmet_prerequisite_are_not_scheduled_together():
    a = Candidate(section=section("a", "SPAN 1002", [("MW", "09:00", "10:20")]), credits=4, requirement_ids=["R1"], priority=1, interest=1)
    b = Candidate(section=section("b", "SPAN 1003", [("TR", "09:00", "10:20")]), credits=4, requirement_ids=["R2"], priority=1, interest=1)
    courses = {"SPAN 1002": course("SPAN 1002", 4), "SPAN 1003": course("SPAN 1003", 4, [["SPAN 1002"]])}
    free = ScheduleModel([a, b], courses, [], prefs(credit_min=4, credit_max=8), {"R1": 1, "R2": 1}, False, []).solve(STRATEGIES[0])
    assert len(free.sections) == 2
    seq = ScheduleModel([a, b], courses, [], prefs(credit_min=4, credit_max=8), {"R1": 1, "R2": 1}, False, [],
                        sequence_pairs=[("SPAN 1002", "SPAN 1003")]).solve(STRATEGIES[0])
    assert seq.feasible and len(seq.sections) == 1


def test_bulletin_index_search_finds_the_program_page():
    from app.adapters.bulletin_live import BulletinIndexSearch, FetchResult
    sitemap = "".join(f"<loc>https://bulletin.temple.edu/undergraduate/{p}/</loc>" for p in
                      ("liberal-arts/psychology-ba", "liberal-arts/psychology-minor", "liberal-arts/clinical-health-psychology-minor",
                       "science-technology/biology-ba"))

    class Fake:
        def get(self, url):
            return FetchResult(url, sitemap, "cache", None)
    hits = BulletinIndexSearch(Fake(), {}).search("Psychology BA requirements Temple University", "major").hits
    assert hits[0].url.endswith("/liberal-arts/psychology-ba/")
    hits = BulletinIndexSearch(Fake(), {}).search("Psychology Minor requirements Temple University", "minor").hits
    assert hits[0].url.endswith("/liberal-arts/psychology-minor/")


def test_fetcher_only_reads_the_bulletin_and_falls_back_when_offline(tmp_path, monkeypatch):
    from app.adapters import bulletin_live
    from app.core.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    f = bulletin_live.BulletinFetcher(live=False)
    assert f.get("https://example.com/x").mode == "unavailable"
    url = "https://bulletin.temple.edu/undergraduate/liberal-arts/psychology-ba/"
    assert f.get(url).mode == "unavailable"
    _, snap = bulletin_live._paths(url)
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text("<html>snapshot</html>")
    r = f.get(url)
    assert r.mode == "snapshot" and r.text == "<html>snapshot</html>" and "disabled" in r.error


# --- research agent in the pipeline ------------------------------------------

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as c:
        yield c


def test_research_agent_runs_first_and_reports_offline_sources(client):
    r = client.post("/api/plans", json={"student_id": "demo-lina"})
    plan = client.get(f"/api/plans/{r.json()['plan_id']}").json()
    assert [a["agent"] for a in plan["agents"]][:3] == ["academic_profile", "requirements_research", "degree_requirements"]
    rr = plan["state"]["requirements_research"]
    assert rr["live_enabled"] is False
    assert all(p["fetch"]["mode"] in ("snapshot", "unavailable") for p in rr["programs"] if p["fetch"])
    research = next(a for a in plan["agents"] if a["agent"] == "requirements_research")
    assert research["decision"]["task"] and research["log"]


def test_research_agent_replaces_rules_when_the_live_page_differs(client, monkeypatch):
    """If the bulletin page today lists different courses, the plan uses the page."""
    from app.adapters import bulletin_live
    page = """<h1 class="page-title">Psychology BA</h1><div id="requirementstextcontainer"><h2>Required</h2>
<table class="sc_courselist"><tbody><tr class="odd"><td class="codecol"><a class="bubblelink code">PSY 1001</a></td><td>Intro</td><td class="hourscol">3</td></tr>
<tr class="even"><td class="codecol"><a class="bubblelink code">PSY 9999</a></td><td>New course</td><td class="hourscol">3</td></tr></tbody></table></div>"""

    def fake_get(self, url):
        hit = "/liberal-arts/psychology" in url
        res = bulletin_live.FetchResult(url, page if hit else None, "live" if hit else "unavailable", "2026-11-03T00:00:00+00:00")
        self.results.append(res)
        return res
    monkeypatch.setattr(bulletin_live.BulletinFetcher, "get", fake_get)
    sid = client.post("/api/students", json={
        "name": "T", "academic_year": "Junior", "expected_graduation": "2028-05", "planning_term": "202703", "programs": ["PSY-BA"],
        "credit_target": 12, "credit_min": 3, "credit_max": 18, "consent_to_process": True, "transcript": [], "availability": []}).json()
    auth = {"Authorization": f"Bearer {sid['access_token']}"}
    progs = client.get("/api/catalog/programs").json()
    if not next(p for p in progs if p["id"] == "PSY-BA")["source_url"]:
        pytest.skip("fixture program has no bulletin URL")
    plan = client.get(f"/api/plans/{client.post('/api/plans', json={'student_id': sid['id']}, headers=auth).json()['plan_id']}", headers=auth).json()
    entry = plan["state"]["requirements_research"]["programs"][0]
    assert entry["changes"]["added"] >= 1
    names = [r["name"] for r in plan["state"]["degree_requirements"]["requirements"] if r["program_id"] == "PSY-BA"]
    assert any("PSY 9999" in n for n in names)


# --- real Temple data ---------------------------------------------------------

@pytest.mark.skipif(not (REAL / "programs.json").exists(), reason="real Temple dataset not present")
def test_every_temple_major_has_school_and_university_layers():
    progs = {p["id"]: p for p in json.loads((REAL / "programs.json").read_text())["programs"]}
    majors = [p for p in progs.values() if p["type"] == "major"]
    assert len(majors) >= 200
    for p in majors:
        assert "layer-university" in p["layers"], p["id"]
        assert any(progs[l]["type"] == "school" for l in p["layers"]), p["id"]
        assert all(l in progs for l in p["layers"]), p["id"]
    for p in progs.values():
        for l in p.get("layers", []):
            assert progs[l]["type"] in ("school", "university")
    layer_rules = [r for p in progs.values() if p["type"] in ("school", "university") for r in p["requirements"]]
    assert all(r.get("evidence") for r in layer_rules)
    # every transcribed school rule was found verbatim on its page at ingest time
    assert all(r["evidence_found"] for r in layer_rules if not r["id"].endswith("-wi"))


# --- change requests: phrasing coverage, questions, warnings -------------------

@pytest.mark.parametrize("msg,expected", [
    ("I have soccer practice MWF 3-5pm", [("M", "15:00", "17:00"), ("W", "15:00", "17:00"), ("F", "15:00", "17:00")]),
    ("I'm busy Tuesday 1-3pm", [("T", "13:00", "15:00")]),
    ("I work weekends", [("S", "09:00", "17:00"), ("U", "09:00", "17:00")]),
])
def test_parser_reads_day_abbreviations_and_busy_times(msg, expected):
    from app.agents.constraints import _regex_parse
    got = [(c.day, c.start, c.end) for c in _regex_parse(msg).changes if c.action == "add_unavailable"]
    assert got == expected


def test_parser_maps_common_preferences():
    from app.agents.constraints import _regex_parse
    acts = lambda m: [(c.action, c.time or c.day or c.credits) for c in _regex_parse(m).changes]  # noqa: E731
    assert acts("I can't do Wednesdays") == [("day_off", "W")]
    assert acts("No classes after 6pm") == [("avoid_after", "18:00")]
    assert ("avoid_before", "10:00") in acts("I hate mornings")
    assert acts("make it lighter") == [("adjust_credits", -3)]
    assert "online-only" in _regex_parse("Only online classes please").unclear[0]


def test_questions_are_answered_not_executed_and_consequences_are_warned(client):
    pid = client.post("/api/plans", json={"student_id": "demo-lina"}).json()["plan_id"]
    client.get(f"/api/plans/{pid}")
    q = client.post(f"/api/plans/{pid}/modify", json={"message": "Can I drop PSY 2201?"}).json()
    assert q["rerun"] is False and q["applied"] == [] and "question" in q["unclear"][0]
    r = client.post(f"/api/plans/{pid}/modify", json={"message": "I want 21 credits"}).json()
    assert r["rerun"] and any("overload" in w and "dean" in w for w in r["warnings"])


def test_alternatives_are_verified_and_priorities_explained(client):
    pid = client.post("/api/plans", json={"student_id": "demo-lina"}).json()["plan_id"]
    st = client.get(f"/api/plans/{pid}").json()["state"]
    so = st["schedule_optimization"]
    assert so["candidate_pool"]["considered"] <= so["candidate_pool"]["eligible_courses"] and "maximizes" in so["objective"]
    assert all(o["weights"]["w_req"] > 0 for o in so["options"])
    alts = [a for o in st["student_explanation"]["options"] for c in o["courses"] for a in c["alternatives_considered"]]
    assert alts and all(a["method"] != "heuristic" for a in alts)
    assert all(a["verified"] or a["method"] == "not re-checked" for a in alts)
    for c in st["graduation_planning"]["priorities"].values():
        assert abs(sum(b["value"] for b in c["basis"]) - c["priority"]) < 0.01


def test_failed_prerequisite_does_not_allow_same_term_pairing():
    from app.agents.base import Catalog, PlanContext
    from app.agents.optimization import sequence_pairs
    from app.domain import PlanningPreferences, StudentProfile
    student = StudentProfile(id="s", name="s", academic_year="Junior", expected_graduation="2028-05", catalog_year=None, planning_term="202703",
                             program_ids=[], campus="Main", f1_status="no", interests_text="", availability=[],
                             transcript=[TranscriptItem(course="FIN 3901", status="completed", grade="F")],
                             preferences=PlanningPreferences(credit_min=3, credit_max=18, credit_target=12))
    cs = {"FIN 3504": course("FIN 3504"), "FIN 3507": course("FIN 3507", 3, [["FIN 3901", "FIN 3504", "@OTHER"]])}
    ctx = PlanContext(db=None, plan_id="p", student=student, state={},
                      catalog=Catalog(term_id="202703", term_name="Spring 2027", courses=cs, sections=[], requirements=[], programs={},
                                      double_count_allowed=set()))
    assert ("FIN 3504", "FIN 3507") in sequence_pairs(ctx, ["FIN 3504", "FIN 3507"])


def test_interest_matching_uses_the_students_own_phrases_not_a_topic_list():
    from app.agents.interests import detect_themes, fallback_scores
    themes = detect_themes("I'm interested in health policy, jazz and urban farming", [])
    assert themes == ["Health policy", "Jazz", "Urban farming"]
    courses = {"A 1": {"title": "Health Policy in America", "description": "Policy making for public health systems."},
               "B 1": {"title": "Jazz History", "description": "Improvisation and jazz ensembles."},
               "C 1": {"title": "Organic Chemistry", "description": "Reactions and mechanisms."}}
    s = fallback_scores(themes, courses)
    assert s["A 1"]["score"] > 0 and s["B 1"]["score"] > 0 and s["C 1"]["score"] == 0
    assert "Health policy" in s["A 1"]["reason"] and s["A 1"]["method"] == "tfidf_similarity"
