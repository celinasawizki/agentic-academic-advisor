"""Constraint-based schedule optimization with Google OR-Tools CP-SAT.

Hard constraints are encoded behind enforcement literals so that, when a model
is infeasible, we can ask CP-SAT for the assumptions responsible and shrink
them to an irreducible conflicting set with a deletion filter."""

from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from app.core.config import settings
from app.domain import AvailBlock, CourseData, PlanningPreferences, SectionData
from app.rules import earliest_start, overlapping_blocks, to_minutes, within_blocks

SCALE = 100
FREE_ELECTIVE = "FREE_ELECTIVE"


def _tenths(credits: float) -> int:
    return int(round(credits * 10))


@dataclass
class Candidate:
    section: SectionData
    credits: float
    requirement_ids: list[str]
    priority: float  # 0..1 degree-progress value from Graduation agent
    interest: float  # 0..1 from Interest agent


@dataclass
class Strategy:
    key: str
    label: str
    w_req: int
    w_int: int
    w_soft: int
    w_dev: int = 4
    enforce_critical: bool = False
    # Max interest-based electives that satisfy no requirement. They are a fallback only: the
    # solver first builds the term from requirement courses and adds a free elective only when
    # those can't reach the credit minimum/target.
    free_electives: int = 2


# Degree progress dominates every strategy: w_int × interest (≤ w_int × 100 per course) stays below
# the gap between an individually required course and a GenEd/range match (~0.3 × w_req × 100), so
# interest decides *which* requirement options to take, never whether to take a requirement.
STRATEGIES = [
    Strategy("graduation", "Graduation Priority", w_req=10, w_int=1, w_soft=3, enforce_critical=True),
    Strategy("interest", "Interest Priority", w_req=10, w_int=3, w_soft=3),
    Strategy("balance", "Work-Life Balance", w_req=4, w_int=1, w_soft=14),
]


@dataclass
class HardGroup:
    key: str
    kind: str  # availability | credit_min | credit_max | must_course | locked_section | f1_full_time
    description: str


@dataclass
class SolveResult:
    feasible: bool
    sections: list[SectionData] = field(default_factory=list)
    credits: float = 0
    objective: float = 0
    breakdown: dict = field(default_factory=dict)
    soft_violations: list[dict] = field(default_factory=list)
    conflict_set: list[HardGroup] = field(default_factory=list)
    conflict_set_minimal: bool = False


class ScheduleModel:
    def __init__(
        self,
        candidates: list[Candidate],
        courses: dict[str, CourseData],
        blocks: list[AvailBlock],
        prefs: PlanningPreferences,
        requirement_caps: dict[str, int | tuple[int, dict[str, int]]],
        f1: bool,
        must_courses: list[str],
        student_required: list[str] | None = None,
        sequence_pairs: list[tuple[str, str]] | None = None,
        plan_mode: bool = False,
    ):
        # plan_mode: the student's graduation plan fixes the courses (passed as student_required);
        # the solver only chooses sections. Requirement caps and free-elective limits don't apply,
        # and exclude_sets hold section ids so alternate options differ by section, not by course.
        self.plan_mode = plan_mode
        self.sequence_pairs = sequence_pairs or []  # (prerequisite, course) that can't share a term
        self.c = candidates
        self.courses = courses
        self.blocks = blocks
        self.prefs = prefs
        self.caps = requirement_caps
        self.f1 = f1
        self.must = [c for c in must_courses if c not in (student_required or [])]
        self.student_required = student_required or []

    def _conflict_pairs(self) -> list[tuple[str, str]]:
        if getattr(self, "_pairs", None) is None:
            by_day: dict[str, list[tuple[int, int, str, str]]] = {}
            for cand in self.c:
                for mt in cand.section.meetings:
                    for d in mt.days:
                        by_day.setdefault(d, []).append((to_minutes(mt.start), to_minutes(mt.end), cand.section.id,
                                                         f"{cand.section.course}|{cand.section.component}"))
            pairs: set[tuple[str, str]] = set()
            for items in by_day.values():
                items.sort()
                for i, (s1, e1, id1, c1) in enumerate(items):
                    for s2, e2, id2, c2 in items[i + 1:]:
                        if s2 >= e1:
                            break
                        if c1 != c2:
                            pairs.add((min(id1, id2), max(id1, id2)))
            self._pairs = sorted(pairs)
        return self._pairs

    def hard_groups(self) -> list[HardGroup]:
        groups: dict[str, HardGroup] = {}
        for b in self.blocks:
            if b.kind == "hard":
                k = f"avail:{b.label or 'Unavailable'}"
                groups.setdefault(k, HardGroup(k, "availability", f"Unavailable: {b.label or 'blocked time'}"))
        groups["credit_min"] = HardGroup("credit_min", "credit_min", f"At least {self.prefs.credit_min} credits")
        groups["credit_max"] = HardGroup("credit_max", "credit_max", f"At most {self.prefs.credit_max} credits")
        for c in self.must:
            groups[f"must:{c}"] = HardGroup(f"must:{c}", "must_course", f"Include graduation-critical {c}")
        for c in self.student_required:
            groups[f"req:{c}"] = HardGroup(f"req:{c}", "student_required",
                                           f"Include {c} ({'your graduation plan' if self.plan_mode else 'your request'})")
        for s in self.prefs.locked_sections:
            groups[f"lock:{s}"] = HardGroup(f"lock:{s}", "locked_section", f"Keep locked section {s}")
        if self.f1:
            groups["f1"] = HardGroup("f1", "f1_full_time", f"F-1: {settings.f1_full_time_credits} credits must count toward full course of study (max {settings.f1_max_online_credits_counted} online)")
        return list(groups.values())

    def _build(self, strategy: Strategy, enabled: set[str], exclude_sets: list[set[str]], free_cap: int = 0):
        m = cp_model.CpModel()
        x = {cand.section.id: m.NewBoolVar(cand.section.id) for cand in self.c}
        lit = {g.key: m.NewBoolVar(g.key) for g in self.hard_groups()}
        by_course: dict[str, dict[str, list[str]]] = {}
        for cand in self.c:
            by_course.setdefault(cand.section.course, {}).setdefault(cand.section.component, []).append(cand.section.id)
        y = {}
        for course, comps in by_course.items():
            y[course] = m.NewBoolVar(f"y_{course}")
            if "primary" not in comps:
                m.Add(y[course] == 0)
            for sids in comps.values():
                # one section of every component (lecture, lab, recitation) when the course is taken
                m.Add(sum(x[s] for s in sids) == y[course])

        for a_id, b_id in self._conflict_pairs():
            m.Add(x[a_id] + x[b_id] <= 1)
        for pre, course in self.sequence_pairs:
            if pre in y and course in y:
                m.Add(y[pre] + y[course] <= 1)

        for cand in self.c:
            for blk in overlapping_blocks(cand.section, [b for b in self.blocks if b.kind == "hard"]):
                m.Add(x[cand.section.id] == 0).OnlyEnforceIf(lit[f"avail:{blk.label or 'Unavailable'}"])

        credits = sum(_tenths(cand.credits) * x[cand.section.id] for cand in self.c if cand.section.component == "primary")
        m.Add(credits >= self.prefs.credit_min * 10).OnlyEnforceIf(lit["credit_min"])
        m.Add(credits <= self.prefs.credit_max * 10).OnlyEnforceIf(lit["credit_max"])

        for prefix, codes in (("must", self.must), ("req", self.student_required)):
            for c in codes:
                if c in y:
                    m.Add(y[c] == 1).OnlyEnforceIf(lit[f"{prefix}:{c}"])
                else:
                    m.AddBoolOr([]).OnlyEnforceIf(lit[f"{prefix}:{c}"])  # no eligible section at all
        for s in self.prefs.locked_sections:
            if s in x:
                m.Add(x[s] == 1).OnlyEnforceIf(lit[f"lock:{s}"])
            else:
                m.AddBoolOr([]).OnlyEnforceIf(lit[f"lock:{s}"])

        course_reqs: dict[str, set[str]] = {}
        for cand in self.c:
            if cand.section.component != "primary":
                continue
            course_reqs.setdefault(cand.section.course, set()).update(cand.requirement_ids)
        for req_id, spec in ({} if self.plan_mode else self.caps).items():
            cap, weights = spec if isinstance(spec, tuple) else (spec, {})
            members = [(weights.get(c, 1), y[c]) for c, rids in course_reqs.items() if req_id in rids]
            if sum(w for w, _ in members) > cap:
                m.Add(sum(w * v for w, v in members) <= cap)

        if self.f1:
            prim = [cand for cand in self.c if cand.section.component == "primary"]
            in_person = sum(_tenths(cand.credits) * x[cand.section.id] for cand in prim if cand.section.modality == "in_person"
                            or (cand.section.modality == "hybrid" and settings.f1_hybrid_counts_as_in_person))
            online = sum(_tenths(cand.credits) * x[cand.section.id] for cand in prim if cand.section.modality == "online")
            counted = m.NewIntVar(0, settings.f1_max_online_credits_counted * 10, "online_counted")
            m.Add(counted <= online)
            m.Add(in_person + counted >= settings.f1_full_time_credits * 10).OnlyEnforceIf(lit["f1"])

        free = [] if self.plan_mode else [y[c] for c, rids in course_reqs.items() if rids <= {FREE_ELECTIVE}]
        if free:
            m.Add(sum(free) <= free_cap)

        for prev in exclude_sets:
            present = [x[s] for s in prev if s in x] if self.plan_mode else [y[c] for c in prev if c in y]
            if present:
                m.Add(sum(present) <= len(prev) - 1)

        soft_terms = []
        for cand in self.c:
            soft_terms.append(self._soft_penalty(cand.section) * x[cand.section.id])
        dev = m.NewIntVar(0, 400, "dev")
        m.Add(dev >= credits - self.prefs.credit_target * 10)
        m.Add(dev >= self.prefs.credit_target * 10 - credits)

        # Degree priority and interest are per-course values: count them once per course taken (y),
        # not once per selected section, or a course with lecture + lab + recitation would count 3x.
        prio, intr = self._course_values()
        req_terms = sum(int(prio[c] * SCALE) * y[c] for c in y)
        int_terms = sum(int(intr[c] * SCALE) * y[c] for c in y)
        # A free elective earns no degree value and costs a full requirement's worth, so it only
        # enters the schedule to close a credit gap that no requirement course can fill.
        free_cost = strategy.w_req * SCALE * sum(free) if free else 0
        m.Maximize(strategy.w_req * req_terms + strategy.w_int * int_terms - free_cost
                   - strategy.w_soft * sum(soft_terms) - strategy.w_dev * (SCALE // 10) * dev)

        assumptions = [lit[k] for k in lit if k in enabled]
        for k, v in lit.items():
            if k not in enabled:
                m.Add(v == 0)
        m.AddAssumptions(assumptions)
        return m, x, lit

    def _course_values(self) -> tuple[dict[str, float], dict[str, float]]:
        """Per-course degree priority and interest. Every section of a course carries the same
        values from build_model; the primary (lecture) component's values win if they differ."""
        prio: dict[str, float] = {}
        intr: dict[str, float] = {}
        for cand in sorted(self.c, key=lambda cd: cd.section.component == "primary"):
            prio[cand.section.course] = cand.priority
            intr[cand.section.course] = cand.interest
        return prio, intr

    def _soft_penalty(self, s: SectionData) -> int:
        p = 0
        for blk in overlapping_blocks(s, [b for b in self.blocks if b.kind == "soft"]):
            p += 60
        preferred = [b for b in self.blocks if b.kind == "preferred"]
        if preferred and s.meetings and not within_blocks(s, preferred):
            p += 25
        start = earliest_start(s)
        if start is not None and self.prefs.avoid_before and start < to_minutes(self.prefs.avoid_before):
            p += 50
        if start is not None and self.prefs.prefer_later:
            p += max(0, (12 * 60 - start) // 15)
        if start is not None and self.prefs.avoid_after:
            if any(to_minutes(m.end) > to_minutes(self.prefs.avoid_after) for m in s.meetings):
                p += 50
        return p

    def soft_violations(self, sections: list[SectionData]) -> list[dict]:
        out = []
        for s in sections:
            for blk in overlapping_blocks(s, [b for b in self.blocks if b.kind == "soft"]):
                out.append({"preference": blk.label or "Soft-blocked time", "section": s.id, "course": s.course,
                            "detail": f"{s.course} meets during '{blk.label}' ({blk.day} {blk.start}-{blk.end})."})
            start = earliest_start(s)
            if start is not None and self.prefs.avoid_before and start < to_minutes(self.prefs.avoid_before):
                out.append({"preference": f"No classes before {self.prefs.avoid_before}", "section": s.id, "course": s.course,
                            "detail": f"{s.course} starts before {self.prefs.avoid_before}."})
            if self.prefs.avoid_after and any(to_minutes(m.end) > to_minutes(self.prefs.avoid_after) for m in s.meetings):
                out.append({"preference": f"No classes after {self.prefs.avoid_after}", "section": s.id, "course": s.course,
                            "detail": f"{s.course} ends after {self.prefs.avoid_after}."})
        return out

    def solve(self, strategy: Strategy, exclude_sets: list[set[str]] | None = None, disabled: set[str] | None = None) -> SolveResult:
        groups = self.hard_groups()
        enabled = {g.key for g in groups} - (disabled or set())
        if not strategy.enforce_critical:
            enabled -= {g.key for g in groups if g.kind == "must_course"}
        def run(free_cap: int):
            m, x, _ = self._build(strategy, enabled, exclude_sets or [], free_cap)
            solver = cp_model.CpSolver()
            solver.parameters.max_time_in_seconds = 5
            solver.parameters.num_workers = 1
            return solver, x, solver.Solve(m)

        # Phase 1: requirement courses only. Phase 2 (fallback): allow free electives when the
        # requirement courses alone can't make a valid term or reach the credit target.
        solver, x, status = run(0)
        ok = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        short = ok and sum(c.credits for c in self.c if c.section.component == "primary" and solver.Value(x[c.section.id])) < self.prefs.credit_target
        if strategy.free_electives and (not ok or short):
            s2, x2, st2 = run(strategy.free_electives)
            if st2 in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                solver, x, status, ok = s2, x2, st2, True
        if not ok:
            core = self._minimal_core(strategy, enabled, exclude_sets or [], solver)
            return SolveResult(False, conflict_set=core, conflict_set_minimal=True)
        chosen = [cand for cand in self.c if solver.Value(x[cand.section.id])]
        sections = [cand.section for cand in chosen]
        prio, intr = self._course_values()
        taken = sorted({cand.section.course for cand in chosen})
        return SolveResult(
            True, sections=sections, credits=round(sum(c.credits for c in chosen if c.section.component == "primary"), 1), objective=solver.ObjectiveValue(),
            breakdown={
                # per course, matching the objective (a lab/recitation adds no extra degree value)
                "degree_progress": round(sum(prio[c] for c in taken), 2),
                "interest_alignment": round(sum(intr[c] for c in taken) / max(1, len(taken)), 2),
                "soft_penalty": sum(self._soft_penalty(s) for s in sections),
                "status": "optimal" if status == cp_model.OPTIMAL else "feasible",
            },
            soft_violations=self.soft_violations(sections),
        )

    def _is_feasible(self, strategy: Strategy, enabled: set[str], exclude_sets) -> tuple[bool, list[str]]:
        m, _, lit = self._build(strategy, enabled, exclude_sets, strategy.free_electives)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 5
        solver.parameters.num_workers = 1
        status = solver.Solve(m)
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return True, []
        idx = {v.Index(): k for k, v in lit.items()}
        return False, [idx[i] for i in solver.SufficientAssumptionsForInfeasibility() if i in idx]

    def _minimal_core(self, strategy: Strategy, enabled: set[str], exclude_sets, _solver) -> list[HardGroup]:
        feasible, core = self._is_feasible(strategy, enabled, exclude_sets)
        if feasible:
            return []
        core_set = set(core) or set(enabled)
        for k in sorted(core_set):
            trial = core_set - {k}
            ok, _ = self._is_feasible(strategy, trial, exclude_sets)
            if not ok:
                core_set = trial
        by_key = {g.key: g for g in self.hard_groups()}
        return [by_key[k] for k in sorted(core_set)]

    def check_feasible_without(self, strategy: Strategy, disabled: set[str]) -> SolveResult:
        return self.solve(strategy, disabled=disabled)
