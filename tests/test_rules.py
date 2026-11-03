from helpers import block, course, req, section

from app.domain import TranscriptItem
from app.rules import f1_assessment, overlapping_blocks, prereq_status, requirement_progress, sections_conflict, total_credits


def t(code, status):
    return TranscriptItem(course=code, status=status)


# --- prerequisites ---------------------------------------------------------

def test_prereq_satisfied_by_completed_or_transfer():
    c = course("PSY 2201", prereqs=[["PSY 2101"], ["MATH 1001", "STAT 1001"]])
    assert prereq_status(c, [t("PSY 2101", "completed"), t("STAT 1001", "transfer")]).status == "satisfied"


def test_in_progress_is_not_completed():
    c = course("CIS 3203", prereqs=[["CIS 1068"]])
    r = prereq_status(c, [t("CIS 1068", "in_progress")])
    assert r.status == "conditional"
    assert r.pending_courses == ["CIS 1068"]


def test_prereq_missing_reports_group():
    c = course("PSY 4996", prereqs=[["PSY 2201"]])
    r = prereq_status(c, [t("PSY 2101", "completed"), t("PSY 2201", "planned")])
    assert r.status == "missing"
    assert r.missing_groups == [["PSY 2201"]]


# --- credits ---------------------------------------------------------------

def test_total_credits():
    courses = {"A 1000": course("A 1000", 4), "B 1000": course("B 1000", 3)}
    secs = [section("s1", "A 1000", []), section("s2", "B 1000", [])]
    assert total_credits(secs, courses) == 7


# --- conflicts -------------------------------------------------------------

def test_overlapping_sections_conflict():
    a = section("a", "A 1000", [("TR", "11:00", "12:20")])
    b = section("b", "B 1000", [("R", "12:00", "13:00")])
    assert sections_conflict(a, b)


def test_back_to_back_sections_do_not_conflict():
    a = section("a", "A 1000", [("MW", "10:00", "11:20")])
    b = section("b", "B 1000", [("MW", "11:20", "12:40")])
    assert not sections_conflict(a, b)


def test_online_async_never_conflicts():
    a = section("a", "A 1000", [], modality="online", campus="Online")
    b = section("b", "B 1000", [("MTWRF", "08:00", "22:00")])
    assert not sections_conflict(a, b)


def test_availability_block_overlap():
    s = section("a", "A 1000", [("MW", "14:00", "15:50")])
    assert overlapping_blocks(s, [block("M", "13:00", "18:00")])
    assert not overlapping_blocks(s, [block("T", "13:00", "18:00")])


# --- F-1 counting ----------------------------------------------------------

def _f1(sections_spec):
    courses, secs = {}, []
    for i, (mod, cr) in enumerate(sections_spec):
        code = f"C {1000 + i}"
        courses[code] = course(code, cr)
        secs.append(section(f"s{i}", code, [] if mod == "online" else [("M", "09:00", "10:00")], modality=mod))
    return f1_assessment(secs, courses, "yes")


def test_f1_one_online_course_counts():
    a = _f1([("in_person", 3)] * 3 + [("online", 3)])
    assert a.credits_toward_full_time == 12 and a.status == "meets"


def test_f1_additional_online_allowed_but_not_counted():
    a = _f1([("in_person", 3)] * 4 + [("online", 3), ("online", 3)])
    assert a.status == "meets"  # extra online enrollment is allowed
    assert a.online_credits == 6 and a.online_credits_counted == 3
    assert any("do not count" in n for n in a.notes)


def test_f1_below_full_time_when_online_heavy():
    a = _f1([("in_person", 3)] * 2 + [("online", 3)] * 3)
    assert a.credits_toward_full_time == 9 and a.status == "below"


def test_f1_hybrid_is_not_assumed_in_person():
    a = _f1([("in_person", 3)] * 3 + [("hybrid", 3)])
    assert a.status == "needs_confirmation"


def test_f1_not_applicable_for_domestic():
    courses = {"C 1": course("C 1")}
    assert f1_assessment([section("s", "C 1", [])], courses, "no").status == "not_applicable"


# --- requirement matching --------------------------------------------------

def test_requirement_progress_choose_n():
    r = req("R1", ["A 1", "A 2", "A 3", "A 4"], n=2)
    [p] = requirement_progress([r], [t("A 1", "completed")])
    assert p.remaining_needed == 1 and p.status == "incomplete"
    assert set(p.candidate_courses) == {"A 2", "A 3", "A 4"}


def test_requirement_in_progress_not_complete():
    r = req("R1", ["A 1"])
    [p] = requirement_progress([r], [t("A 1", "in_progress")])
    assert p.remaining_needed == 0 and p.status == "in_progress"


def test_or_alternatives_satisfy_single_requirement():
    r = req("R1", options=[["PSY 1001"], ["PSY 1901"]])
    [p] = requirement_progress([r], [t("PSY 1901", "completed")])
    assert p.status == "complete" and p.completed == ["PSY 1901"]


def test_bundle_requires_every_course():
    r = req("R1", options=[["CHEM 1031", "CHEM 1033"]])
    [p] = requirement_progress([r], [t("CHEM 1031", "completed")])
    assert p.remaining_needed == 1 and set(p.candidate_courses) == {"CHEM 1033"}
    [p] = requirement_progress([r], [t("CHEM 1031", "completed"), t("CHEM 1033", "completed")])
    assert p.status == "complete"


def test_credit_based_requirement():
    courses = {c: course(c, cr) for c, cr in [("S 1", 3), ("S 2", 4), ("S 3", 3)]}
    r = req("R1", ["S 1", "S 2", "S 3"], n=9, kind="credits")
    [p] = requirement_progress([r], [t("S 2", "completed")], courses=courses)
    assert p.remaining_needed == 5 and p.remaining_courses == 2


def test_course_range_and_gened_attribute_patterns():
    courses = {"PSY 3172": course("PSY 3172"), "ART 1001": course("ART 1001")}
    courses["ART 1001"].attributes.append("GA")
    adv = req("ADV", n=1, patterns=[{"subject": "PSY", "min": 3000, "max": 3620}])
    arts = req("GA", n=1, program="GENED", ptype="gened", patterns=[{"attribute": "GA"}])
    out = {p.requirement.id: p for p in requirement_progress([adv, arts], [t("PSY 3172", "completed"), t("ART 1001", "completed")], courses=courses)}
    assert out["ADV"].status == "complete" and out["GA"].status == "complete"


def test_manual_rules_are_not_guessed():
    r = req("R1", kind="manual", n=6)
    [p] = requirement_progress([r], [])
    assert p.status == "manual" and p.remaining_courses == 0


def test_no_double_counting_across_programs_without_rule():
    major = req("M1", ["X 1"], program="MAJ", ptype="major")
    minor = req("N1", ["X 1"], program="MIN", ptype="minor")
    out = {p.requirement.id: p for p in requirement_progress([major, minor], [t("X 1", "completed")])}
    assert out["M1"].completed == ["X 1"]
    assert out["N1"].completed == [] and out["N1"].notes


def test_double_counting_when_explicitly_allowed():
    major = req("M1", ["X 1"], program="MAJ", ptype="major")
    minor = req("N1", ["X 1"], program="MIN", ptype="minor")
    out = {p.requirement.id: p for p in requirement_progress([major, minor], [t("X 1", "completed")], {frozenset({"MAJ", "MIN"})})}
    assert out["N1"].completed == ["X 1"]


def test_placement_alternative_is_conditional_not_missing():
    c = course("PSY 1003", prereqs=[["MATH 0701", "@OTHER"]])
    r = prereq_status(c, [])
    assert r.status == "conditional" and r.unverifiable == [["MATH 0701"]]


def test_change_request_parser_handles_multiple_days_and_times():
    from app.agents.constraints import _regex_parse
    got = [(c.day, c.start, c.end) for c in _regex_parse("I got a job on Tuesdays and Thursdays from 9 to 5").changes]
    assert got == [("T", "09:00", "17:00"), ("R", "09:00", "17:00")]
    assert [(c.day, c.start, c.end) for c in _regex_parse("practice wednesdays 6-9").changes] == [("W", "18:00", "21:00")]
    [c] = _regex_parse("I got a job on Tuesdays.").changes
    assert c.assumption  # unstated hours are an explicit, surfaced assumption
