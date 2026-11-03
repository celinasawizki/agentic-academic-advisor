"""Deterministic academic rules engine. No LLM calls: these functions are the
source of truth for eligibility, conflicts, credits and F-1 counting."""

from dataclasses import dataclass, field

from app.core.config import settings
from app.domain import AvailBlock, CourseData, RequirementData, SectionData, TranscriptItem

SUPPORTED_CAMPUSES = {"Main", "Online"}
COMPLETED_STATUSES = {"completed", "transfer"}
PROGRAM_PRIORITY = {"major": 0, "minor": 1, "certificate": 2, "gened": 3}


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


def meets_on(section: SectionData, day: str) -> bool:
    return any(d == day for d, _, _ in _intervals(section))


def earliest_start(section: SectionData) -> int | None:
    iv = _intervals(section)
    return min(s for _, s, _ in iv) if iv else None


def latest_end(section: SectionData) -> int | None:
    iv = _intervals(section)
    return max(e for _, _, e in iv) if iv else None


def campus_supported(section: SectionData) -> bool:
    return section.campus in SUPPORTED_CAMPUSES


@dataclass
class PrereqResult:
    status: str  # satisfied | conditional | missing
    missing_groups: list[list[str]] = field(default_factory=list)
    pending_courses: list[str] = field(default_factory=list)


def prereq_status(course: CourseData, transcript: list[TranscriptItem]) -> PrereqResult:
    """Prereqs are an AND of OR-groups. In-progress courses are NOT treated as
    completed; they make the prerequisite 'conditional' on passing them."""
    done = {t.course for t in transcript if t.status in COMPLETED_STATUSES}
    in_prog = {t.course for t in transcript if t.status == "in_progress"}
    missing, pending = [], []
    for group in course.prereqs:
        if any(c in done for c in group):
            continue
        ip = [c for c in group if c in in_prog]
        if ip:
            pending.append(ip[0])
        else:
            missing.append(group)
    if missing:
        return PrereqResult("missing", missing, pending)
    if pending:
        return PrereqResult("conditional", [], pending)
    return PrereqResult("satisfied")


@dataclass
class RequirementProgress:
    requirement: RequirementData
    completed: list[str]
    in_progress: list[str]
    remaining_needed: int
    candidate_courses: list[str]
    status: str  # complete | in_progress | incomplete
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        r = self.requirement
        return {
            "id": r.id, "program_id": r.program_id, "program_name": r.program_name,
            "program_type": r.program_type, "name": r.name, "rule": r.rule, "needed": r.needed, "courses": r.courses,
            "category": r.category, "catalog_year": r.catalog_year,
            "verification_status": r.verification_status, "source_url": r.source_url,
            "completed": self.completed, "in_progress": self.in_progress,
            "remaining_needed": self.remaining_needed, "candidate_courses": self.candidate_courses,
            "status": self.status, "notes": self.notes,
        }


def requirement_progress(
    requirements: list[RequirementData],
    transcript: list[TranscriptItem],
    double_count_allowed: set[frozenset[str]] | None = None,
) -> list[RequirementProgress]:
    """Allocate transcript courses to requirements. A course counts once per
    program; it only counts across programs when a double-count rule allows it.
    Without an explicit rule we do not assume double counting."""
    double_count_allowed = double_count_allowed or set()
    status_of = {t.course: t.status for t in transcript}
    used_by_program: dict[str, set[str]] = {}
    owner: dict[str, str] = {}
    ordered = sorted(requirements, key=lambda r: (PROGRAM_PRIORITY.get(r.program_type, 9), r.id))
    out: list[RequirementProgress] = []
    for req in ordered:
        used = used_by_program.setdefault(req.program_id, set())
        completed, in_progress, notes = [], [], []
        for c in req.courses:
            st = status_of.get(c)
            if st is None or st in ("planned", "unverified"):
                continue
            if c in used:
                continue
            other = owner.get(c)
            if other and other != req.program_id and frozenset({other, req.program_id}) not in double_count_allowed:
                notes.append(f"{c} already applied to {other}; double counting not verified for this program.")
                continue
            if len(completed) + len(in_progress) >= req.needed:
                break
            (completed if st in COMPLETED_STATUSES else in_progress).append(c)
            used.add(c)
            owner.setdefault(c, req.program_id)
        remaining = max(0, req.needed - len(completed) - len(in_progress))
        taken = set(completed) | set(in_progress)
        candidates = [c for c in req.courses if c not in taken and status_of.get(c) not in COMPLETED_STATUSES | {"in_progress"}] if remaining else []
        status = "complete" if not remaining and not in_progress else ("in_progress" if not remaining else "incomplete")
        out.append(RequirementProgress(req, completed, in_progress, remaining, candidates, status, notes))
    return out


def total_credits(sections: list[SectionData], courses: dict[str, CourseData]) -> int:
    return sum(courses[s.course].credits for s in sections)


@dataclass
class F1Assessment:
    applies: bool
    in_person_credits: int = 0
    online_credits: int = 0
    hybrid_credits: int = 0
    unknown_credits: int = 0
    online_credits_counted: int = 0
    credits_toward_full_time: int = 0
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
        cr = courses[s.course].credits
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
        a.notes.append(f"Only {a.credits_toward_full_time} credits count toward the {a.full_time_required}-credit full course of study.")
    if a.online_credits > settings.f1_max_online_credits_counted:
        a.notes.append(f"{a.online_credits} online credits scheduled; only {settings.f1_max_online_credits_counted} count toward full-time status. Additional online credits are allowed but do not count.")
    return a
