"""Regression: minimum prerequisite grades with +/- must not be truncated.

The old pattern ended in ``\\b``, which cannot match after "-" or "+" followed by a
space, so "Minimum grade of C- in X" parsed as "C" and students with exactly C- were
wrongly blocked."""

import pytest
from helpers import course

from app.domain import TranscriptItem
from app.rules import prereq_status


def _course(text, prereqs=(("MATH 1041",),)):
    c = course("MATH 1042", prereqs=[list(g) for g in prereqs])
    c.prereq_text = text
    return c


@pytest.mark.parametrize("text,expected", [
    ("Minimum grade of C- in MATH 1041.", "C-"),
    ("Minimum grade of C- in MATH 1041", "C-"),
    ("Minimum grade of B+ in MATH 1041 or placement.", "B+"),
    ("minimum grade of c- in MATH 1041", "C-"),
    ("Minimum grade of C in MATH 1041.", "C"),
    ("Minimum grade of C-", "C-"),
    ("Minimum grade of D, in MATH 1041", "D"),
    ("(MATH 1041, Minimum grade of C-)", "C-"),
    ("MATH 1041 or permission of instructor.", None),
    ("", None),
])
def test_min_prereq_grade_keeps_plus_minus(text, expected):
    assert _course(text).min_prereq_grade == expected


def _status(text, grade):
    return prereq_status(_course(text), [TranscriptItem(course="MATH 1041", status="completed", grade=grade)]).status


def test_exact_c_minus_satisfies_c_minus_prerequisite():
    assert _status("Minimum grade of C- in MATH 1041.", "C-") == "satisfied"
    assert _status("Minimum grade of C- in MATH 1041.", "D+") == "missing"


def test_b_plus_minimum_is_enforced_not_truncated_to_b():
    assert _status("Minimum grade of B+ in MATH 1041.", "B+") == "satisfied"
    assert _status("Minimum grade of B+ in MATH 1041.", "B") == "missing"


def test_plain_c_minimum_unchanged():
    assert _status("Minimum grade of C in MATH 1041.", "C") == "satisfied"
    assert _status("Minimum grade of C in MATH 1041.", "C-") == "missing"
