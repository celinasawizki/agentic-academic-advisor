"""Degree priority and interest count once per course, not once per selected component section.

Regression: a GenEd with lecture + lab + recitation used to count its priority 3x and beat a
mandatory course competing for the same time slot (reported degree_progress 1.05)."""

from helpers import course, prefs, section

from app.optimizer import STRATEGIES, Candidate, ScheduleModel


def _sec(sid, code, meetings, component="primary"):
    s = section(sid, code, meetings)
    s.component = component
    return s


def _cand(sec, priority, interest=0.5, req="R"):
    credits = 3 if sec.component == "primary" else 0
    return Candidate(section=sec, credits=credits, requirement_ids=[req], priority=priority, interest=interest)


def _scenario():
    # The mandatory course and the GenEd lecture meet at the same time; only one fits a 3-credit term.
    required = _cand(_sec("req-001", "MAJ 2001", [("MW", "10:00", "11:20")]), priority=0.6, req="MAJOR")
    gened = [
        _cand(_sec("gen-001", "GEN 1001", [("MW", "10:00", "11:20")]), priority=0.35, req="GENED"),
        _cand(_sec("gen-lab", "GEN 1001", [("T", "14:00", "15:50")], component="Lab"), priority=0.35, req="GENED"),
        _cand(_sec("gen-rec", "GEN 1001", [("R", "14:00", "14:50")], component="Recitation"), priority=0.35, req="GENED"),
    ]
    cands = [required, *gened]
    courses = {c.section.course: course(c.section.course, 3) for c in cands}
    p = prefs(credit_min=3, credit_max=3, credit_target=3)
    return ScheduleModel(cands, courses, [], p, {"MAJOR": 1, "GENED": 1}, False, [])


def test_required_course_beats_multi_component_gened_every_strategy():
    m = _scenario()
    for strat in STRATEGIES:
        res = m.solve(strat)
        assert res.feasible
        assert {s.course for s in res.sections} == {"MAJ 2001"}, strat.key
        assert res.breakdown["degree_progress"] == 0.6


def test_breakdown_counts_multi_component_course_once():
    m = _scenario()
    forced = ScheduleModel(m.c, m.courses, m.blocks, m.prefs, m.caps, m.f1, m.must, student_required=["GEN 1001"])
    res = forced.solve(STRATEGIES[0])
    assert res.feasible and len(res.sections) == 3  # lecture + lab + recitation
    assert res.breakdown["degree_progress"] == 0.35  # not 1.05
    assert res.breakdown["interest_alignment"] == 0.5
    # The forced alternative must score below the unforced best (verified_alternatives relies on this).
    assert res.objective < m.solve(STRATEGIES[0]).objective
