"""Deterministic change-request parser (no ANTHROPIC_API_KEY): soft vs hard wording, per-clause parsing,
time reading, course swaps, and question detection."""

import pytest

from app.agents.constraints import _hour, _parse_range, _regex_parse, is_question


def parsed(msg):
    return [(c.action, c.day, c.start, c.end, c.strength) for c in _regex_parse(msg).changes]


def blocks(msg):
    return [(c.day, c.start, c.end, c.strength) for c in _regex_parse(msg).changes if c.action == "add_unavailable"]


# --- A. soft wording never becomes a hard block --------------------------------

@pytest.mark.parametrize("msg", ["I'd prefer Fridays off because of work", "I would like Fridays off for my club",
                                 "I’d prefer Fridays off because of work"])
def test_soft_day_off_with_job_word_is_a_soft_preference(msg):
    assert parsed(msg) == [("day_off", "F", None, None, "soft")]


def test_no_classes_after_time_on_a_day_is_a_time_preference_not_a_day_off():
    cs = _regex_parse("No classes after 6pm on Fridays").changes
    assert [(c.action, c.day, c.start, c.end, c.strength) for c in cs] == [("add_unavailable", "F", "18:00", "22:00", "soft")]
    assert parsed("No classes on Fridays after 6pm") == [("add_unavailable", "F", "18:00", "22:00", "soft")]


def test_no_classes_before_time_on_a_day_blocks_only_the_morning():
    assert parsed("No classes before 10 on Mondays") == [("add_unavailable", "M", "07:00", "10:00", "soft")]


def test_part_of_day_blocks_that_window_not_the_whole_day():
    [c] = _regex_parse("I can't do Tuesday mornings").changes
    assert (c.action, c.day, c.start, c.end) == ("add_unavailable", "T", "07:00", "12:00") and c.assumption
    [c] = _regex_parse("I'd prefer no Thursday evenings").changes
    assert (c.day, c.start, c.end, c.strength) == ("R", "17:00", "22:00", "soft")


def test_each_clause_keeps_its_own_days_times_and_intent():
    assert parsed("I work Mondays 3-5pm and want Fridays off") == [
        ("add_unavailable", "M", "15:00", "17:00", "hard"), ("day_off", "F", None, None, "hard")]
    assert blocks("I have practice, Mondays 3-5") == [("M", "15:00", "17:00", "hard")]
    assert blocks("I work Mondays and Wednesdays 3-5pm") == [("M", "15:00", "17:00", "hard"), ("W", "15:00", "17:00", "hard")]


@pytest.mark.parametrize("text,expected", [
    ("8-10pm", ("20:00", "22:00")), ("9-5pm", ("09:00", "17:00")), ("11-1pm", ("11:00", "13:00")), ("12-3", ("12:00", "15:00")),
    ("9pm-12am", ("21:00", "24:00")), ("6-9", ("18:00", "21:00")), ("9 to 5", ("09:00", "17:00")), ("1 pm to 6 pm", ("13:00", "18:00")),
    ("10pm-2am", None),
])
def test_parse_range_meridiem_inheritance(text, expected):
    assert _parse_range(text) == expected


def test_unreadable_hours_never_fabricate_a_block():
    r = _regex_parse("I work Fridays 10pm-2am")
    assert r.changes == [] and "couldn't read the hours" in r.unclear[0]
    assert blocks("I work Fridays 8-10pm") == [("F", "20:00", "22:00", "hard")]
    assert blocks("I work Fridays 9pm-12am") == [("F", "21:00", "24:00", "hard")]


@pytest.mark.parametrize("h,ap,ctx,expected", [
    ("12", None, "after", "12:00"), ("12", None, "", "12:00"), ("12", "am", "", "00:00"), ("12", "pm", "", "12:00"),
    ("7", None, "after", "19:00"), ("9", None, "after", "21:00"), ("3", None, "after", "15:00"),
    ("9", None, "before", "09:00"), ("10", None, "before", "10:00"), ("2", None, "before", "14:00"), ("6", "pm", "after", "18:00"),
])
def test_hour_reads_bare_times_in_context(h, ap, ctx, expected):
    assert _hour(h, None, ap, ctx)[0] == expected


def test_bare_times_in_requests_are_read_as_class_hours_and_the_assumption_is_surfaced():
    [c] = _regex_parse("No classes after 7").changes
    assert (c.action, c.time) == ("avoid_after", "19:00") and "7:00 PM" in c.assumption
    assert [(c.action, c.time) for c in _regex_parse("No classes after 12").changes] == [("avoid_after", "12:00")]
    assert [(c.action, c.time) for c in _regex_parse("I need to be done by 3").changes] == [("avoid_after", "15:00")]
    assert [(c.action, c.time) for c in _regex_parse("No classes before 9").changes] == [("avoid_before", "09:00")]


def test_relative_credit_changes_are_not_absolute_targets():
    assert [(c.action, c.credits) for c in _regex_parse("drop 3 credits").changes] == [("adjust_credits", -3)]
    assert [(c.action, c.credits) for c in _regex_parse("add 3 more credits").changes] == [("adjust_credits", 3)]
    assert [(c.action, c.credits) for c in _regex_parse("I want 12 credits").changes] == [("set_credits", 12)]


# --- B. replace / swap excludes only the outgoing course -----------------------

@pytest.mark.parametrize("msg", ["Replace PSY 3096 with PSY 3101", "Swap PSY 3096 for PSY 3101", "Take PSY 3101 instead of PSY 3096",
                                 "Instead of PSY 3096, take PSY 3101", "swap psy3096 for psy3101"])
def test_replace_excludes_only_the_course_being_replaced(msg):
    got = [(c.action, c.course) for c in _regex_parse(msg).changes]
    assert sorted(got) == [("exclude_course", "PSY 3096"), ("include_course", "PSY 3101")]


def test_course_verbs_apply_per_clause():
    got = [(c.action, c.course) for c in _regex_parse("drop PSY 1001 and add PSY 2201").changes]
    assert got == [("exclude_course", "PSY 1001"), ("include_course", "PSY 2201")]
    got = [(c.action, c.course) for c in _regex_parse("Drop PSY 1001 and PSY 2201").changes]
    assert got == [("exclude_course", "PSY 1001"), ("exclude_course", "PSY 2201")]


# --- C. questions vs polite requests ---------------------------------------------

@pytest.mark.parametrize("msg", ["Can I drop PSY 3096", "Can I drop PSY 3096?", "What happens if I drop PSY 3096?",
                                 "what if I take 12 credits", "Would it delay graduation to drop PSY 3096",
                                 "Is it possible to have Fridays off", "Why is PSY 3096 in my plan", "Should I drop PSY 3096"])
def test_questions_are_detected_without_a_question_mark(msg):
    assert is_question(msg)


@pytest.mark.parametrize("msg", ["Can you give me Fridays off?", "Could you make my schedule lighter?", "Please drop PSY 3096",
                                 "Give me Fridays off", "Drop PSY 3096", "I work MWF 3-5pm"])
def test_polite_requests_are_requests(msg):
    assert not is_question(msg)


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as c:
        yield c


def test_question_leaves_settings_unchanged_and_polite_request_applies(client):
    pid = client.post("/api/plans", json={"student_id": "demo-lina"}).json()["plan_id"]
    before = client.get(f"/api/plans/{pid}").json()["state"]["_student"]
    for q in ("Can I drop PSY 2201", "What happens if I drop PSY 2201?"):
        r = client.post(f"/api/plans/{pid}/modify", json={"message": q}).json()
        assert r["rerun"] is False and r["applied"] == [] and "question" in r["unclear"][0]
    assert client.get(f"/api/plans/{pid}").json()["state"]["_student"] == before
    r = client.post(f"/api/plans/{pid}/modify", json={"message": "Can you give me Fridays off?"}).json()
    assert r["rerun"] and any("Fridays off" in a for a in r["applied"])


# --- must keep working -------------------------------------------------------------

def test_existing_phrasings_still_parse():
    assert blocks("I have soccer practice MWF 3-5pm") == [("M", "15:00", "17:00", "hard"), ("W", "15:00", "17:00", "hard"),
                                                         ("F", "15:00", "17:00", "hard")]
    assert blocks("I'm busy Tuesday 1-3pm") == [("T", "13:00", "15:00", "hard")]
    assert blocks("I got a job on Tuesdays and Thursdays from 9 to 5") == [("T", "09:00", "17:00", "hard"), ("R", "09:00", "17:00", "hard")]
    assert [(c.label, c.day, c.start, c.end) for c in _regex_parse("I just got a job on Tuesdays from 1 PM to 6 PM. Find another schedule.").changes] \
        == [("Job", "T", "13:00", "18:00")]
    [c] = _regex_parse("I work weekends").changes[:1]
    assert c.assumption and (c.start, c.end) == ("09:00", "17:00")
    assert parsed("Give me Fridays off") == [("day_off", "F", None, None, "hard")]
    assert parsed("I'd prefer Fridays off") == [("day_off", "F", None, None, "soft")]
    assert parsed("I can't do Wednesdays") == [("day_off", "W", None, None, "hard")]
    assert [(c.action, c.time) for c in _regex_parse("No classes after 6pm").changes] == [("avoid_after", "18:00")]
    assert ("avoid_before", "10:00") in [(c.action, c.time) for c in _regex_parse("I hate mornings").changes]
    assert [(c.action, c.credits) for c in _regex_parse("make it lighter").changes] == [("adjust_credits", -3)]
    assert [(c.action, c.credits) for c in _regex_parse("I want to take 18 credits instead").changes] == [("set_credits", 18)]
    assert [(c.action, c.course) for c in _regex_parse("Drop PSY 3096").changes] == [("exclude_course", "PSY 3096")]
    assert "online-only" in _regex_parse("Only online classes please").unclear[0]
