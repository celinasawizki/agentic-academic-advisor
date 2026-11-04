import re
from typing import Literal

from pydantic import BaseModel

from app.agents.base import Agent, PlanContext
from app.agents.llm import structured_call, wrap_untrusted
from app.core.config import settings
from app.domain import AvailBlock, SectionData, StudentProfile
from app.models import SchedulingConstraint
from app.rules import overlapping_blocks

DAY_NAMES = {"monday": "M", "tuesday": "T", "wednesday": "W", "thursday": "R", "friday": "F", "saturday": "S", "sunday": "U"}


class SchedulingConstraintsAgent(Agent):
    key = "scheduling_constraints"
    title = "Scheduling & Constraint Agent"
    responsibility = "Turns availability, credit load, campus and enrollment rules into typed hard/soft constraints for the optimizer."

    def run(self, ctx: PlanContext) -> dict:
        s, p = ctx.student, ctx.student.preferences
        hard, soft, academic, immigration = [], [], [], []
        for b in s.availability:
            prefix = "Preferred time" if b.kind == "preferred" else (b.label or "Blocked")
            item = {"code": f"avail_{b.kind}", "description": f"{prefix}: {b.day} {b.start}-{b.end}", "params": b.model_dump()}
            (hard if b.kind == "hard" else soft if b.kind == "soft" else soft).append(item)
        hard.append({"code": "credit_range", "description": f"Between {p.credit_min} and {p.credit_max} credits", "params": {"min": p.credit_min, "max": p.credit_max}})
        hard.append({"code": "campus", "description": "Main Campus or online sections only (prototype scope)", "params": {"campuses": ["Main", "Online"]}})
        hard.append({"code": "no_time_conflicts", "description": "No two selected sections may overlap", "params": {}})
        for sec in p.locked_sections:
            hard.append({"code": "locked_section", "description": f"Keep {sec}", "params": {"section": sec}})
        soft.append({"code": "credit_target", "description": f"Aim for {p.credit_target} credits", "params": {"target": p.credit_target}})
        if p.avoid_before:
            soft.append({"code": "avoid_before", "description": f"Avoid classes before {p.avoid_before}", "params": {"time": p.avoid_before}})
        if p.avoid_after:
            soft.append({"code": "avoid_after", "description": f"Avoid classes ending after {p.avoid_after}", "params": {"time": p.avoid_after}})
        if p.prefer_later:
            soft.append({"code": "prefer_later", "description": "Prefer later start times", "params": {}})
        academic.append({"code": "prerequisites", "description": "Every course must have prerequisites completed or in progress", "params": {}})
        academic.append({"code": "requirement_caps", "description": "Do not exceed the number of courses a requirement still needs", "params": {}})
        if s.f1_status == "yes":
            immigration.append({"code": "f1_full_course_of_study",
                                "description": (f"At least {settings.f1_full_time_credits} credits must count toward full course of study; "
                                                f"at most {settings.f1_max_online_credits_counted} online credits count. "
                                                f"Hybrid counts as in-person: {settings.f1_hybrid_counts_as_in_person}."),
                                "params": {"full_time": settings.f1_full_time_credits, "max_online_counted": settings.f1_max_online_credits_counted}})
            ctx.log("F-1 rule applied: limits how online credits COUNT toward full-time status; it does not cap online enrollment.")

        grad = ctx.state["graduation_planning"]
        pre_checks = []
        eligible = [SectionData(**e["section"]) for e in ctx.state["course_discovery"]["eligible_sections"]]
        offered = {x.course for x in eligible}
        critical = [c["course"] for c in grad["critical_courses"]]
        for c in critical:
            if c not in offered:
                pre_checks.append({"course": c, "issue": "critical_not_available",
                                   "detail": f"Graduation-critical {c} cannot be taken this term (no eligible section or prerequisite missing)."})
        for c in p.deferred_courses:
            pre_checks.append({"course": c, "issue": "deferred_by_student", "detail": f"You chose to defer {c}; it is not required in this term's plans."})
        must = [c for c in critical if c in offered and c not in p.deferred_courses] + list(p.required_courses)
        hard_blocks = [b for b in s.availability if b.kind == "hard"]
        soft_blocks = [b for b in s.availability if b.kind == "soft"]
        for c in [c for c in must if c not in p.required_courses]:
            secs = [x for x in eligible if x.course == c]
            free = [x for x in secs if not overlapping_blocks(x, hard_blocks)]
            if not secs:
                pre_checks.append({"course": c, "issue": "no_eligible_section", "detail": f"{c} has no eligible section this term."})
            elif not free:
                pre_checks.append({"course": c, "issue": "all_sections_hard_blocked",
                                   "detail": f"Every section of {c} overlaps a hard availability block."})
            elif all(overlapping_blocks(x, soft_blocks) for x in free):
                labels = sorted({b.label for x in free for b in overlapping_blocks(x, soft_blocks)})
                pre_checks.append({"course": c, "issue": "requires_soft_violation",
                                   "detail": f"The only compatible section(s) of {c} conflict with your preference: {', '.join(labels)}."})
        for t in p.accepted_tradeoffs:
            ctx.log(f"Student accepted a tradeoff earlier: gave up '{t}'.")
        for pc in pre_checks:
            ctx.log(f"Pre-check: {pc['detail']}")

        ctx.db.query(SchedulingConstraint).filter_by(plan_id=ctx.plan_id).delete()
        for kind, items in (("hard", hard), ("soft", soft), ("academic", academic), ("immigration", immigration)):
            for it in items:
                ctx.db.add(SchedulingConstraint(plan_id=ctx.plan_id, kind=kind, code=it["code"], description=it["description"], params=it["params"]))
        ctx.log(f"Prepared {len(hard)} hard, {len(soft)} soft, {len(academic)} academic and {len(immigration)} immigration constraints")
        return {"hard": hard, "soft": soft, "academic": academic, "immigration": immigration,
                "must_courses_graduation_strategy": must, "pre_checks": pre_checks}

    def decision(self, ctx, o):
        return {"task": "Translate availability, credit load, campus and enrollment rules into typed constraints",
                "data_sources": ["Student availability and preferences", "F-1 planning rule (configurable)", "Graduation Planning Agent output"],
                "findings": [self.summarize(o), f"Must-include for Graduation Priority: {', '.join(o['must_courses_graduation_strategy']) or 'none'}"],
                "recommendation": "Hard constraints are never violated automatically; soft ones only with student approval.",
                "validation": {"status": "warnings" if o["pre_checks"] else "passed", "detail": f"{len(o['pre_checks'])} pre-check finding(s)"},
                "unresolved": [p["detail"] for p in o["pre_checks"][:6]]}

    def summarize(self, o: dict) -> str:
        return (f"{len(o['hard'])} hard, {len(o['soft'])} soft, {len(o['academic'])} academic, {len(o['immigration'])} immigration constraints; "
                f"{len(o['pre_checks'])} pre-check warning(s).")


# ---- Natural-language change requests -------------------------------------

class ChangeOut(BaseModel):
    action: Literal["day_off", "add_unavailable", "set_credits", "adjust_credits", "prefer_later", "avoid_before", "avoid_after",
                    "boost_interest", "exclude_course", "include_course", "lock_section", "unlock_section"]
    day: Literal["M", "T", "W", "R", "F", "S", "U"] | None = None
    start: str | None = None
    end: str | None = None
    strength: Literal["hard", "soft"] | None = None
    credits: int | None = None
    time: str | None = None
    term: str | None = None
    course: str | None = None
    section: str | None = None
    label: str | None = None
    assumption: str | None = None


class ChangeSetOut(BaseModel):
    changes: list[ChangeOut]
    unclear: list[str]


TIME_RANGE_RE = re.compile(r"(\d{1,2})(?::(\d\d))?\s*(am|pm)?\s*(?:-|–|to|until|till)\s*(\d{1,2})(?::(\d\d))?\s*(am|pm)?")


def _parse_range(t: str) -> tuple[str, str] | None:
    m = TIME_RANGE_RE.search(t)
    if not m:
        return None
    sh, sm, sa, eh, em, ea = int(m.group(1)), m.group(2) or "00", m.group(3), int(m.group(4)), m.group(5) or "00", m.group(6)
    if (sa == "pm" and sh < 12) or (sa is None and sh < 7):
        sh += 12
    if (ea == "pm" and eh < 12) or (ea is None and eh < sh and eh + 12 > sh):
        eh += 12
    if not (0 <= sh < 24 and 0 < eh <= 24 and sh < eh):
        return None
    return f"{sh:02d}:{sm}", f"{eh:02d}:{em}"


DAY_TOKEN = {"mon": "M", "monday": "M", "tue": "T", "tues": "T", "tuesday": "T", "wed": "W", "wednesday": "W",
             "thu": "R", "thur": "R", "thurs": "R", "thursday": "R", "fri": "F", "friday": "F", "sat": "S", "saturday": "S",
             "sun": "U", "sunday": "U"}
DAY_LABEL = {"M": "Monday", "T": "Tuesday", "W": "Wednesday", "R": "Thursday", "F": "Friday", "S": "Saturday", "U": "Sunday"}
LETTER_DAYS = re.compile(r"\b(mwf|mw|tr|tth|tuth|mtwr|mtwrf|mtwthf|wf|mf)\b")
JOB_RE = re.compile(r"\b(job|work|internship|practice|shift|rehearsal|volunteer|training|game|team|club|caregiving|commute)\w*")


def _days(t: str) -> list[str]:
    """Day codes mentioned in text, in order: names, abbreviations, letter runs (MWF, TR) and weekends/weekdays."""
    found: list[str] = []
    for m in re.finditer(r"\b(mon|monday|tue|tues|tuesday|wed|wednesday|thu|thur|thurs|thursday|fri|friday|sat|saturday|sun|sunday)s?\b"
                         r"|\b(weekends?|weekdays)\b|" + LETTER_DAYS.pattern, t):
        if m.group(1):
            found.append(DAY_TOKEN[m.group(1)])
        elif m.group(2):
            found += ["S", "U"] if m.group(2).startswith("weekend") else ["M", "T", "W", "R", "F"]
        else:
            run = m.group(0).replace("th", "R").replace("tu", "T").upper()
            found += [ch for ch in run if ch in "MTWRF"]
    return list(dict.fromkeys(found))


def _hour(h: str, mm: str | None, ap: str | None) -> str:
    hour = int(h) % 12 + (12 if ap == "pm" or (ap is None and int(h) < 7) else 0)
    return f"{hour:02d}:{mm or '00'}"


def _regex_parse(text: str) -> ChangeSetOut:
    t = text.lower()
    changes: list[ChangeOut] = []
    unclear: list[str] = []
    job = JOB_RE.search(t)
    days = _days(t)
    rng = _parse_range(t)
    off = re.search(r"\boff\b|no (classes|class|school)( on)?|free (on )?|can'?t (do|make|come)|cannot (do|make)|not available|unavailable|busy", t)
    for d in days:
        name = DAY_LABEL[d]
        if job or (rng and off):
            label = job.group(1).title() if job else "Unavailable"
            if rng:
                changes.append(ChangeOut(action="add_unavailable", day=d, start=rng[0], end=rng[1], strength="hard", label=label))
            else:
                changes.append(ChangeOut(action="add_unavailable", day=d, start="09:00", end="17:00", strength="hard", label=label,
                                         assumption=f"Hours not specified; assumed 9:00 AM-5:00 PM on {name}. Adjust in the availability editor."))
        elif off:
            strength = "soft" if re.search(r"prefer|ideally|if possible|would like|rather", t) else "hard"
            changes.append(ChangeOut(action="day_off", day=d, strength=strength, label=f"{name}s off"))
    if m := re.search(r"(\d{1,2})\s*credits?", t):
        changes.append(ChangeOut(action="set_credits", credits=int(m.group(1))))
    elif re.search(r"\b(lighter|fewer credits|less (work|load|credits)|reduce (my )?(load|credits)|lower (my )?(load|credits))\b", t):
        changes.append(ChangeOut(action="adjust_credits", credits=-3, assumption="Interpreted 'lighter' as 3 fewer credits (about one course)."))
    elif re.search(r"\b(heavier|more credits|add (a|one more) course)\b", t):
        changes.append(ChangeOut(action="adjust_credits", credits=3, assumption="Interpreted this as 3 more credits (about one course)."))
    if re.search(r"later in the day|sleep in|no (early|morning)|later classes|move .* later|hate mornings|not a morning person|mornings are", t):
        changes.append(ChangeOut(action="prefer_later"))
        changes.append(ChangeOut(action="avoid_before", time="10:00", assumption="Interpreted 'later' as avoiding classes before 10:00 AM (soft)."))
    if m := re.search(r"no (?:classes|class) before (\d{1,2})(?::(\d\d))?\s*(am|pm)?", t):
        changes.append(ChangeOut(action="avoid_before", time=_hour(m.group(1), m.group(2), m.group(3) or "am")))
    if m := re.search(r"(?:no (?:classes|class)|nothing) (?:after|past) (\d{1,2})(?::(\d\d))?\s*(am|pm)?|done by (\d{1,2})(?::(\d\d))?\s*(am|pm)?", t):
        g = m.groups()
        h, mm, ap = (g[0], g[1], g[2]) if g[0] else (g[3], g[4], g[5])
        changes.append(ChangeOut(action="avoid_after", time=_hour(h, mm, ap)))
    if m := re.search(r"(?:more|related to|about|something (?:in|with))\s+(?:courses? )?(?:related to |about |on )?([a-z][a-z \-]{1,40}?)(?:[.!?,]|$| courses| classes| instead)", t):
        term = m.group(1).strip()
        if term not in {"the", "a", "my", "credits", "credit", "course", "work", "load"} and not re.match(r"\d", term):
            changes.append(ChangeOut(action="boost_interest", term=term))
    codes = re.findall(r"\b([A-Z]{2,5})\s?(\d{4})\b", text.upper())
    for subj, num in codes:
        code = f"{subj} {num}"
        if re.search(r"replace|drop|remove|exclude|don'?t want|without|swap", t):
            changes.append(ChangeOut(action="exclude_course", course=code))
        elif re.search(r"\b(add|include|take|need)\b", t):
            changes.append(ChangeOut(action="include_course", course=code))
    if not changes:
        if re.search(r"\bonline\b", t):
            unclear.append("An online-only filter isn't supported yet. You can exclude specific courses, or block times you can't attend in person. "
                           "If you're on an F-1 visa, at most 3 online credits count toward full-time status.")
        elif re.search(r"\bundo|revert|go back|never ?mind\b", t):
            unclear.append("Undo isn't supported yet. Change availability or preferences directly, or start a new plan from the dashboard.")
        else:
            unclear.append("I couldn't map that request to a schedule change. Try e.g. 'Give me Fridays off', 'I work MWF 3-5pm', "
                           "'No classes after 6pm' or 'I want 12 credits'.")
    return ChangeSetOut(changes=changes, unclear=unclear)


QUESTION_RE = re.compile(r"^\s*(can|could|should|would|what if|is it ok|am i able|may)\b.*\?\s*$", re.I | re.S)
OVERLOAD_POLICY = ("Temple Academic Bulletin, Academic Course Load: \"Academic overloads (19 or more semester hours) during fall and spring "
                   "semesters need special approval of the dean or dean's designee\" and \"Credits over 18 carry additional tuition charges.\"")


def parse_change_request(text: str, current_courses: list[str]) -> tuple[ChangeSetOut, str]:
    result = structured_call(
        system=("You convert a student's schedule change request into structured changes for a deterministic schedule optimizer. "
                "Use day codes M T W R F S U and 24h HH:MM times. 'Give me X off' / 'I can't' / jobs are hard; 'prefer' / 'ideally' are soft. "
                "If hours or details are missing, choose a conservative default and explain it in 'assumption'. "
                "Put anything you cannot map into 'unclear'. Only reference courses that appear in the current schedule list or that the student names explicitly."),
        user=wrap_untrusted("student_request", text) + f"\nCourses in the current schedule: {', '.join(current_courses)}",
        schema=ChangeSetOut,
    )
    if result is not None:
        return result, "llm"
    return _regex_parse(text), "deterministic"


def apply_changes(student: StudentProfile, cs: ChangeSetOut, required: dict[str, list[str]] | None = None,
                  warnings: list[str] | None = None) -> tuple[StudentProfile, list[str], list[str]]:
    """Apply a parsed change set. `required` maps course -> requirement names it is the only option for, so excluding
    it can be flagged; consequences are appended to `warnings`."""
    st = student.model_copy(deep=True)
    p = st.preferences
    applied, assumptions = [], []
    warnings = warnings if warnings is not None else []
    for c in cs.changes:
        if c.assumption:
            assumptions.append(c.assumption)
        if c.action == "day_off" and c.day:
            st.availability = [b for b in st.availability if not (b.day == c.day and b.start == "07:00" and b.end == "22:00")]
            st.availability.append(AvailBlock(day=c.day, start="07:00", end="22:00", kind=c.strength or "soft", label=c.label or f"{c.day} off"))
            applied.append(f"{c.label or c.day + ' off'} set as a {'HARD constraint' if c.strength == 'hard' else 'soft preference'}")
        elif c.action == "add_unavailable" and c.day and c.start and c.end:
            st.availability.append(AvailBlock(day=c.day, start=c.start, end=c.end, kind=c.strength or "hard", label=c.label or "Unavailable"))
            applied.append(f"Added {c.strength or 'hard'} block: {c.label or 'Unavailable'} {c.day} {c.start}-{c.end}")
        elif c.action in ("set_credits", "adjust_credits") and c.credits:
            target = c.credits if c.action == "set_credits" else max(1, min(24, p.credit_target + c.credits))
            p.credit_target = target
            p.credit_max = max(p.credit_max, target)
            p.credit_min = min(p.credit_min, target)
            applied.append(f"Credit target set to {target}")
            if target > 18:
                warnings.append(f"{target} credits is an academic overload. {OVERLOAD_POLICY}")
            if student.f1_status == "yes" and target < settings.f1_full_time_credits:
                warnings.append(f"{target} credits is below the {settings.f1_full_time_credits}-credit full course of study for F-1 students; "
                                "a reduced course load needs ISSS authorization before you register.")
        elif c.action == "prefer_later":
            p.prefer_later = True
            applied.append("Prefer later start times (soft)")
        elif c.action == "avoid_before" and c.time:
            p.avoid_before = c.time
            applied.append(f"Avoid classes before {c.time} (soft)")
        elif c.action == "avoid_after" and c.time:
            p.avoid_after = c.time
            applied.append(f"Avoid classes ending after {c.time} (soft)")
        elif c.action == "boost_interest" and c.term:
            if c.term not in p.interest_boost_terms:
                p.interest_boost_terms.append(c.term)
            applied.append(f"Boost courses related to '{c.term}'")
        elif c.action == "exclude_course" and c.course:
            p.excluded_courses.append(c.course)
            p.required_courses = [x for x in p.required_courses if x != c.course]
            applied.append(f"Excluded {c.course}")
            for why in (required or {}).get(c.course, []):
                warnings.append(f"{c.course} is required for {why}; excluding it postpones that requirement, it doesn't remove it.")
        elif c.action == "include_course" and c.course:
            p.required_courses.append(c.course)
            applied.append(f"Require {c.course} if an eligible section exists")
        elif c.action == "lock_section" and c.section:
            p.locked_sections.append(c.section)
            applied.append(f"Locked {c.section}")
        elif c.action == "unlock_section" and c.section:
            p.locked_sections = [s for s in p.locked_sections if s != c.section]
            applied.append(f"Unlocked {c.section}")
    return st, applied, assumptions
