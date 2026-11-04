from helpers import block, course, prefs, section

from app.optimizer import STRATEGIES, Candidate, ScheduleModel

GRAD, INTEREST, BALANCE = STRATEGIES


def cand(sec, credits=3, req_ids=("R",), priority=0.5, interest=0.5):
    return Candidate(section=sec, credits=credits, requirement_ids=list(req_ids), priority=priority, interest=interest)


def model(cands, blocks=(), p=None, caps=None, f1=False, must=()):
    courses = {c.section.course: course(c.section.course, c.credits) for c in cands}
    return ScheduleModel(cands, courses, list(blocks), p or prefs(), caps or {"R": 10}, f1, list(must))


def test_never_selects_conflicting_sections():
    a = cand(section("a", "A 1", [("TR", "11:00", "12:20")]), interest=1)
    b = cand(section("b", "B 1", [("TR", "12:00", "13:20")]), interest=1)
    c = cand(section("c", "C 1", [("MW", "09:00", "10:20")]))
    res = model([a, b, c]).solve(INTEREST)
    ids = {s.id for s in res.sections}
    assert res.feasible and not {"a", "b"} <= ids


def test_hard_constraint_enforced_even_when_valuable():
    work = cand(section("w", "A 1", [("M", "14:00", "15:00")]), priority=1, interest=1)
    other = cand(section("o", "B 1", [("T", "09:00", "10:00")]))
    res = model([work, other], blocks=[block("M", "13:00", "18:00")], p=prefs(credit_min=3)).solve(GRAD)
    assert res.feasible and [s.id for s in res.sections] == ["o"]


def test_soft_preference_optimized():
    fri = cand(section("f", "A 1", [("F", "09:00", "10:00")]))
    tue = cand(section("t", "A 1", [("T", "09:00", "10:00")]))
    res = model([fri, tue], blocks=[block("F", "07:00", "22:00", "soft", "Fridays off")], p=prefs(credit_min=3, credit_target=3)).solve(BALANCE)
    assert [s.id for s in res.sections] == ["t"] and not res.soft_violations


def test_soft_preference_violated_and_reported_when_needed():
    fri = cand(section("f", "A 1", [("F", "09:00", "10:00")]), priority=1)
    res = model([fri], blocks=[block("F", "07:00", "22:00", "soft", "Fridays off")], p=prefs(credit_min=3, credit_target=3),
                must=["A 1"]).solve(GRAD)
    assert res.feasible and res.soft_violations[0]["preference"] == "Fridays off"


def test_credit_range_respected():
    cands = [cand(section(f"s{i}", f"C {i}", [("MTWRF"[i % 5], f"{8 + i}:00".zfill(5), f"{8 + i}:50".zfill(5))])) for i in range(6)]
    res = model(cands, p=prefs(credit_min=9, credit_max=12, credit_target=12)).solve(INTEREST)
    assert 9 <= res.credits <= 12


def test_infeasibility_returns_minimal_conflict_set():
    only = cand(section("p", "PSY 2201", [("F", "09:00", "11:50")]), credits=4, priority=1)
    filler = cand(section("x", "X 1", [("T", "09:00", "10:00")]))
    m = model([only, filler], blocks=[block("F", "07:00", "22:00", "hard", "Fridays off")],
              p=prefs(credit_min=3, credit_target=7), must=["PSY 2201"])
    res = m.solve(GRAD)
    assert not res.feasible and res.conflict_set_minimal
    assert {g.key for g in res.conflict_set} == {"avail:Fridays off", "must:PSY 2201"}
    # Relaxing either constraint in the set restores feasibility.
    for g in res.conflict_set:
        assert m.solve(GRAD, disabled={g.key}).feasible


def test_f1_rule_limits_counted_online_credits():
    onl = [cand(section(f"o{i}", f"O {i}", [], modality="online", campus="Online"), interest=1) for i in range(4)]
    inp = [cand(section(f"p{i}", f"P {i}", [("MTWRF"[i], "09:00", "09:50")]), interest=0) for i in range(4)]
    res = model(onl + inp, f1=True, p=prefs(credit_min=12, credit_max=15, credit_target=12)).solve(INTEREST)
    in_person = sum(3 for s in res.sections if s.modality == "in_person")
    online = sum(3 for s in res.sections if s.modality == "online")
    assert res.feasible and in_person + min(online, 3) >= 12


def test_requirement_cap():
    cands = [cand(section(f"s{i}", f"E {i}", [("MTWRF"[i], "09:00", "09:50")]), req_ids=("ELEC",), interest=1) for i in range(4)]
    res = model(cands, caps={"ELEC": 2}, p=prefs(credit_min=3, credit_target=12)).solve(INTEREST)
    assert len(res.sections) == 2


def test_alternative_schedules_differ():
    cands = [cand(section(f"s{i}", f"C {i}", [("MTWRF"[i], "09:00", "09:50")])) for i in range(5)]
    m = model(cands, p=prefs(credit_min=6, credit_max=6, credit_target=6))
    first = m.solve(GRAD)
    second = m.solve(INTEREST, exclude_sets=[{s.course for s in first.sections}])
    assert {s.course for s in first.sections} != {s.course for s in second.sections}


def test_course_components_are_scheduled_together_without_clashing():
    lec = cand(section("lec1", "PHYS 1061", [("TR", "11:00", "12:20")]), credits=4)
    lab_clash = section("lab1", "PHYS 1061", [("T", "11:30", "13:30")])
    lab_ok = section("lab2", "PHYS 1061", [("W", "09:00", "11:00")])
    labs = [cand(lab_clash.model_copy(update={"component": "Lab"}), credits=0),
            cand(lab_ok.model_copy(update={"component": "Lab"}), credits=0)]
    res = model([lec, *labs], p=prefs(credit_min=4, credit_target=4)).solve(INTEREST)
    assert res.feasible and {s.id for s in res.sections} == {"lec1", "lab2"} and res.credits == 4


def test_select_one_requirement_takes_one_option_even_with_bundles():
    phys = cand(section("p", "PHYS 1021", [("M", "09:00", "10:00")]), req_ids=("SCI",), interest=1)
    biol = cand(section("b", "BIOL 1111", [("T", "09:00", "10:00")]), req_ids=("SCI",), interest=1)
    chem = cand(section("c", "CHEM 1031", [("W", "09:00", "10:00")]), req_ids=("SCI",), interest=1)
    chem_lab = cand(section("cl", "CHEM 1033", [("R", "09:00", "10:00")]), req_ids=("SCI",), interest=1)
    caps = {"SCI": (1, {"PHYS 1021": 1, "BIOL 1111": 1, "CHEM 1031": 1, "CHEM 1033": 0})}
    res = model([phys, biol, chem, chem_lab], caps=caps, p=prefs(credit_min=3, credit_target=12)).solve(INTEREST)
    taken = {s.course for s in res.sections}
    assert len(taken & {"PHYS 1021", "BIOL 1111", "CHEM 1031"}) == 1


def test_interest_never_displaces_requirement_courses():
    """A high-interest course that satisfies no requirement must not take a slot that a
    requirement course could fill, even under the Interest strategy."""
    req = cand(section("r", "MKTG 2101", [("T", "09:00", "10:20")]), req_ids=("R",), priority=0.68, interest=0.0)
    gen = cand(section("g", "ECE 0832", [("M", "09:00", "10:20")]), req_ids=("G",), priority=0.33, interest=0.93)
    free = cand(section("f", "JUDO 1098", [("W", "09:00", "10:20")]), req_ids=("FREE_ELECTIVE",), priority=0.0, interest=0.91)
    for strat in STRATEGIES:
        res = model([req, gen, free], caps={"R": 1, "G": 1}, p=prefs(credit_min=3, credit_max=6, credit_target=6)).solve(strat)
        assert res.feasible and {s.course for s in res.sections} == {"MKTG 2101", "ECE 0832"}, strat.key


def test_free_elective_only_fills_a_credit_gap():
    req = cand(section("r", "PSY 3096", [("T", "09:00", "10:20")]), req_ids=("R",), priority=1.0)
    free = cand(section("f", "PHIL 3228", [("W", "09:00", "10:20")]), req_ids=("FREE_ELECTIVE",), priority=0.0, interest=0.9)
    res = model([req, free], caps={"R": 1}, p=prefs(credit_min=6, credit_max=6, credit_target=6)).solve(INTEREST)
    assert res.feasible and {s.course for s in res.sections} == {"PSY 3096", "PHIL 3228"}
