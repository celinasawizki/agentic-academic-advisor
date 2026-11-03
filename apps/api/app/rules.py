"""Deterministic academic rules engine. No LLM calls: these functions are the
source of truth for eligibility, conflicts, credits and F-1 counting."""

import math
from dataclasses import dataclass, field

from app.core.config import settings
from app.domain import AvailBlock, CourseData, RequirementData, SectionData, TranscriptItem

SUPPORTED_CAMPUSES = {"Main", "Online"}
COMPLETED_STATUSES = {"completed", "transfer"}
GRADE_SCALE = ["A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F"]
NON_PASSING = {"F", "W", "WF", "WU", "I", "NR", "U", "AU", "X"}
GENED_MIN_GRADE = "C-"  # Bulletin: "All GenEd courses must be completed with a grade of C- or higher"


def grade_ok(grade: str | None, minimum: str | None = None) -> bool:
    """True when a recorded grade passes and meets an optional minimum. Unknown / pass-type
    grades (TR, P, CR, S or none recorded) are accepted; they are verified in the degree audit."""
    g = (grade or "").strip().upper()
    if g in NON_PASSING:
        return False
    if minimum and g in GRADE_SCALE and minimum.upper() in GRADE_SCALE:
        return GRADE_SCALE.index(g) <= GRADE_SCALE.index(minimum.upper())
    return True


def counts_as_done(t: TranscriptItem, minimum: str | None = None) -> bool:
    return t.status in COMPLETED_STATUSES and grade_ok(t.grade, minimum)
PROGRAM_PRIORITY = {"major": 0, "minor": 1, "certificate": 2, "gened": 3}
OTHER = "@OTHER"


def to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _intervals(section: SectionData) -> list[tuple[str, int, int]]:
    return [(d, to_minutes(m.start), to_minutes(m.end)) for m in section.meetings for d in m.days]


def sections_conflict(a: SectionData, b: SectionData) -> bool:
    for d1, s1, e1 in _intervals(a):
        for d2, s2, e2 in _intervals(b):
            if d1 == d2 and s1 < e2 and s2 < e1:
                return True
    return False


def overlapping_blocks(section: SectionData, blocks: list[AvailBlock]) -> list[AvailBlock]:
    hits = []
    for blk in blocks:
        bs, be = to_minutes(blk.start), to_minutes(blk.end)
        if any(d == blk.day and s < be and bs < e for d, s, e in _intervals(section)):
            hits.append(blk)
    return hits


def within_blocks(section: SectionData, blocks: list[AvailBlock]) -> bool:
    """Every meeting falls inside one of the given blocks on its day."""
    for d, s, e in _intervals(section):
        if not any(b.day == d and to_minutes(b.start) <= s and e <= to_minutes(b.end) for b in blocks):
            return False
    return True


def meets_on(section: SectionData, day: str) -> bool:
    return any(d == day for d, _, _ in _intervals(section))


def earliest_start(section: SectionData) -> int | None:
    iv = _intervals(section)
    return min(s for _, s, _ in iv) if iv else None


def latest_end(section: SectionData) -> int | None:
    iv = _intervals(section)
    return max(e for _, _, e in iv) if iv else None


def campus_supported(section: SectionData) -> bool:
    """Main Campus sections, plus online sections regardless of the listed campus."""
    return section.campus in SUPPORTED_CAMPUSES or section.modality == "online"


def section_credits(section: SectionData, courses: dict[str, CourseData]) -> float:
    if section.component != "primary":
        return 0.0
    if section.credits:
        return float(section.credits)
    c = courses.get(section.course)
    return float(c.credits) if c else 3.0


@dataclass
class PrereqResult:
    status: str  # satisfied | conditional | missing
    missing_groups: list[list[str]] = field(default_factory=list)
    pending_courses: list[str] = field(default_factory=list)
    unverifiable: list[list[str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def prereq_status(course: CourseData, transcript: list[TranscriptItem]) -> PrereqResult:
    """Prereqs are an AND of OR-groups. In-progress courses are NOT treated as
    completed; they make the prerequisite 'conditional' on passing them. A group
    that can also be met by placement/test scores (@OTHER) cannot be checked, so
    it is 'conditional' rather than 'missing'."""
    minimum = course.min_prereq_grade
    done = {t.course for t in transcript if counts_as_done(t, minimum)}
    in_prog = {t.course for t in transcript if t.status == "in_progress"}
    notes = [f"{t.course} grade {t.grade} does not meet the required minimum ({minimum or 'passing'})."
             for t in transcript if t.status in COMPLETED_STATUSES and not counts_as_done(t, minimum)
             and any(t.course in g for g in course.prereqs)]
    missing, pending, unverifiable = [], [], []
    for group in course.prereqs:
        if any(c in done for c in group):
            continue
        ip = [c for c in group if c in in_prog]
        if ip:
            pending.append(ip[0])
        elif OTHER in group:
            unverifiable.append([c for c in group if c != OTHER])
        else:
            missing.append(group)
    if missing:
        return PrereqResult("missing", missing, pending, unverifiable, notes)
    if pending or unverifiable:
        return PrereqResult("conditional", [], pending, unverifiable, notes)
    return PrereqResult("satisfied", notes=notes)


@dataclass
class RequirementProgress:
    requirement: RequirementData
    completed: list[str]
    in_progress: list[str]
    remaining_needed: float  # courses for count, credits for credits
    remaining_courses: int  # schedulable course slots still needed
    candidate_courses: list[str]
    status: str  # complete | in_progress | incomplete | manual | note
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        r = self.requirement
        return {
            "id": r.id, "program_id": r.program_id, "program_name": r.program_name, "program_type": r.program_type,
            "group": r.group, "name": r.name, "kind": r.kind, "needed": r.needed, "options": r.options,
            "patterns": r.patterns, "requirement_notes": r.notes, "catalog_year": r.catalog_year,
            "verification_status": r.verification_status, "source_url": r.source_url,
            "completed": self.completed, "in_progress": self.in_progress, "remaining_needed": self.remaining_needed,
            "remaining_courses": self.remaining_courses, "candidate_courses": self.candidate_courses,
            "status": self.status, "notes": self.notes,
        }


def requirement_progress(
    requirements: list[RequirementData],
    transcript: list[TranscriptItem],
    double_count_allowed: set[frozenset[str]] | None = None,
    courses: dict[str, CourseData] | None = None,
) -> list[RequirementProgress]:
    """Allocate transcript courses to requirements. A course counts once per
    program; it only counts across programs when a double-count rule allows it.
    Without an explicit rule we do not assume double counting."""
    double_count_allowed = double_count_allowed or set()
    courses = courses or {}
    status_of = {t.course: t.status for t in transcript if t.status not in ("planned", "unverified")
                 and (t.status == "in_progress" or grade_ok(t.grade))}
    gened_ok = {t.course for t in transcript if t.status == "in_progress" or grade_ok(t.grade, GENED_MIN_GRADE)}
    failed = [t for t in transcript if t.status in COMPLETED_STATUSES and not grade_ok(t.grade)]
    used_by_program: dict[str, set[str]] = {}
    owner: dict[str, str] = {}
    ordered = sorted(requirements, key=lambda r: (PROGRAM_PRIORITY.get(r.program_type, 9), r.kind == "credits", bool(r.patterns), r.id))
    out: list[RequirementProgress] = []

    def available(code: str, req: RequirementData, notes: list[str]) -> bool:
        if code not in status_of or code in used_by_program.setdefault(req.program_id, set()):
            return False
        if req.program_type == "gened" and code not in gened_ok:
            notes.append(f"{code} grade is below the GenEd minimum ({GENED_MIN_GRADE}).")
            return False
        other = owner.get(code)
        if other and other != req.program_id and frozenset({other, req.program_id}) not in double_count_allowed:
            notes.append(f"{code} already applied to another program; double counting not assumed.")
            return False
        return True

    def take(code: str, req: RequirementData) -> None:
        used_by_program.setdefault(req.program_id, set()).add(code)
        owner.setdefault(code, req.program_id)

    for req in ordered:
        notes: list[str] = []
        if req.kind in ("note", "manual"):
            out.append(RequirementProgress(req, [], [], 0, 0, [], req.kind, list(req.notes)))
            continue
        completed, in_progress = [], []
        got = 0.0
        unit = (lambda codes: sum(courses[c].credits if c in courses else 3 for c in codes)) if req.kind == "credits" else (lambda codes: 1)
        for opt in req.options:
            if got >= req.needed:
                break
            if all(available(c, req, notes) for c in opt):
                for c in opt:
                    take(c, req)
                    (completed if status_of[c] in COMPLETED_STATUSES else in_progress).append(c)
                got += unit(opt)
        if req.patterns and got < req.needed:
            for code in list(status_of):
                if got >= req.needed:
                    break
                c = courses.get(code)
                if c and req.pattern_matches(c) and available(code, req, []):
                    take(code, req)
                    (completed if status_of[code] in COMPLETED_STATUSES else in_progress).append(code)
                    got += unit([code])
        for t in failed:
            if any(t.course in o for o in req.options):
                notes.append(f"{t.course} has a non-passing grade ({t.grade}) and does not count.")
        remaining = max(0.0, req.needed - got)
        if req.kind == "credits":
            slots = math.ceil(remaining / 3) if remaining else 0
        else:
            slots = int(math.ceil(remaining))
        taken = set(completed) | set(in_progress)
        candidates = [c for c in dict.fromkeys(req.courses) if c not in taken and c not in status_of] if remaining else []
        status = "complete" if not remaining and not in_progress else ("in_progress" if not remaining else "incomplete")
        out.append(RequirementProgress(req, completed, in_progress, remaining, slots, candidates, status, notes))
    return out


def total_credits(sections: list[SectionData], courses: dict[str, CourseData]) -> float:
    return sum(section_credits(s, courses) for s in sections)


@dataclass
class F1Assessment:
    applies: bool
    in_person_credits: float = 0
    online_credits: float = 0
    hybrid_credits: float = 0
    unknown_credits: float = 0
    online_credits_counted: float = 0
    credits_toward_full_time: float = 0
    full_time_required: int = 0
    status: str = "not_applicable"  # meets | below | needs_confirmation | not_applicable
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def f1_assessment(sections: list[SectionData], courses: dict[str, CourseData], f1_status: str) -> F1Assessment:
    """Counts how online coursework applies toward the F-1 full course of study.
    This is NOT a cap on online enrollment: extra online credits are allowed,
    they just do not count toward the full-time minimum."""
    if f1_status != "yes":
        return F1Assessment(applies=False)
    a = F1Assessment(applies=True, full_time_required=settings.f1_full_time_credits)
    for s in sections:
        cr = section_credits(s, courses)
        if s.modality == "in_person":
            a.in_person_credits += cr
        elif s.modality == "online":
            a.online_credits += cr
        elif s.modality == "hybrid":
            a.hybrid_credits += cr
        else:
            a.unknown_credits += cr
    a.online_credits_counted = min(a.online_credits, settings.f1_max_online_credits_counted)
    hybrid_counted = a.hybrid_credits if settings.f1_hybrid_counts_as_in_person else 0
    a.credits_toward_full_time = a.in_person_credits + a.online_credits_counted + hybrid_counted
    uncertain = (0 if settings.f1_hybrid_counts_as_in_person else a.hybrid_credits) + a.unknown_credits
    if a.credits_toward_full_time >= a.full_time_required:
        a.status = "meets"
        if uncertain:
            a.notes.append("Includes hybrid/unknown-modality courses; their classification was not counted and should be confirmed with ISSS.")
    elif a.credits_toward_full_time + uncertain >= a.full_time_required:
        a.status = "needs_confirmation"
        a.notes.append("Meets the full-time minimum only if hybrid/unknown-modality courses count as in-person. Confirm with Temple's International Student and Scholar Services (ISSS).")
    else:
        a.status = "below"
        a.notes.append(f"Only {a.credits_toward_full_time:g} credits count toward the {a.full_time_required}-credit full course of study.")
    if a.online_credits > settings.f1_max_online_credits_counted:
        a.notes.append(f"{a.online_credits:g} online credits scheduled; only {settings.f1_max_online_credits_counted} count toward full-time status. Additional online credits are allowed but do not count.")
    return a
