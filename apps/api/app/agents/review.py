from app.agents.base import Agent, PlanContext
from app.domain import SectionData
from app.ingest.sections import components_by_course
from app.models import ScheduleCourse, ScheduleOption, ValidationResult
from app.rules import campus_supported, f1_assessment, overlapping_blocks, prereq_status, sections_conflict, total_credits


def review_sections(ctx: PlanContext, sections: list[SectionData], requirement_ids: dict[str, list[str]],
                    components: dict[str, set[str]] | None = None, free_electives: set[str] | None = None) -> list[dict]:
    """Independent re-verification shared by the Academic Review Agent and manual schedule
    validation. Deliberately does not reuse optimizer state.

    requirement_ids: course -> open requirements it may satisfy.
    components: course -> components the term offers (e.g. {"primary", "Lab"}).
    free_electives: interest-based courses that satisfy no parsed requirement."""
    s, p, courses = ctx.student, ctx.student.preferences, ctx.catalog.courses
    components = components or {}
    free_electives = free_electives or set()
    checks: list[dict] = []

    def add(check: str, passed: bool, severity: str, detail: str):
        checks.append({"check": check, "passed": passed, "severity": "info" if passed else severity, "detail": detail})

    keys = [(x.course, x.component) for x in sections]
    add("unique_courses", len(keys) == len(set(keys)), "error", "Each course (and course component) appears once." if len(keys) == len(set(keys)) else "Duplicate course in schedule.")
    primaries = {x.course for x in sections if x.component == "primary"}
    orphans = sorted({x.course for x in sections if x.component != "primary"} - primaries)
    add("components", not orphans, "error", "Every lab/recitation is paired with its course." if not orphans else f"Lab/recitation without its course: {orphans}")
    chosen = {}
    for x in sections:
        chosen.setdefault(x.course, set()).add(x.component)
    for course in sorted(primaries):
        missing = sorted(components.get(course, {"primary"}) - chosen[course])
        if missing:
            add(f"component_missing:{course}", False, "warning",
                f"{course} is also offered with separate {', '.join(missing)} section(s), which are probably required. "
                "Temple's class search does not publish lecture/lab linkage, so this is unverified; choose one in TUportal.")
        extra = sorted(chosen[course] - {"primary"})
        if extra:
            add(f"component_pairing:{course}", False, "warning",
                f"{course}: pairing of the lecture with the selected {', '.join(extra)} section is inferred from schedule types, not "
                "from published registration links. TUportal may require a specific pairing.")
    clashes = [(a.id, b.id) for i, a in enumerate(sections) for b in sections[i + 1:] if sections_conflict(a, b)]
    add("time_conflicts", not clashes, "error", "No overlapping meetings." if not clashes else f"Overlapping sections: {clashes}")
    hard_hits = [(x.course, b.label) for x in sections for b in overlapping_blocks(x, [b for b in s.availability if b.kind == "hard"])]
    add("hard_availability", not hard_hits, "error", "Respects all hard availability blocks." if not hard_hits else f"Violates hard availability: {hard_hits}")
    total = total_credits(sections, courses)
    add("credit_range", p.credit_min <= total <= p.credit_max, "error",
        f"{total:g} credits (allowed {p.credit_min}-{p.credit_max}); lab/recitation components carry no separate credit.")
    for x in sections:
        if x.term_id != ctx.catalog.term_id:
            add(f"term:{x.id}", False, "error", f"{x.id} is not in {ctx.catalog.term_name}.")
        if not campus_supported(x):
            add(f"campus:{x.id}", False, "error", f"{x.id} is at {x.campus}; only Main Campus and online sections are supported.")
        if not x.meetings and x.modality != "online":
            add(f"tba:{x.id}", False, "warning", f"{x.course} §{x.section} has no published meeting time in the snapshot (TBA).")
        if x.seats_available is not None and x.seats_available <= 0:
            add(f"seats:{x.id}", False, "warning", f"{x.course} §{x.section} was full when the snapshot was taken.")
        if x.component != "primary":
            continue
        if x.course not in courses:
            add(f"catalog:{x.course}", False, "error", f"{x.course} is not in the ingested bulletin course catalog; eligibility cannot be checked.")
            continue
        pre = prereq_status(courses[x.course], s.transcript)
        if pre.status == "missing":
            need = " and ".join("(" + " or ".join(g) + ")" for g in pre.missing_groups)
            add(f"prereq:{x.course}", False, "error", f"{x.course} prerequisite not met: {need}." + (f" {'; '.join(pre.notes)}" if pre.notes else ""))
        elif pre.status == "conditional":
            parts = []
            if pre.pending_courses:
                parts.append(f"depends on in-progress {', '.join(pre.pending_courses)} (conditional on passing)")
            if pre.unverifiable:
                parts.append("has a prerequisite that may be met by placement/test scores, which the planner cannot verify")
            add(f"prereq:{x.course}", False, "warning", f"{x.course} {'; '.join(parts)}.")
        if x.linked:
            add(f"linked:{x.course}", False, "warning", f"{x.course} §{x.section} has a linked section that must also be chosen in TUportal.")
        if x.credits_max and x.credits and x.credits_max > x.credits:
            add(f"variable_credits:{x.course}", False, "warning",
                f"{x.course} §{x.section} is variable credit ({x.credits:g}–{x.credits_max:g}); the planner counted {x.credits:g}.")
        if x.course in free_electives:
            add(f"requirement:{x.course}", False, "warning",
                f"{x.course} is an interest-based elective: it does not satisfy a parsed degree requirement and would count only toward general/free elective credit. Confirm with your advisor.")
        elif not requirement_ids.get(x.course):
            add(f"requirement:{x.course}", False, "warning", f"{x.course} is not linked to any open requirement in your programs.")
    if any(x.data_source == "demo_fixture" for x in sections):
        add("section_provenance", False, "warning", "Some section times come from a labeled demo fixture, not Temple course search.")
    elif sections:
        stamp = min(x.retrieved_at for x in sections)[:10]
        add("section_provenance", False, "warning", f"Sections come from a class-search snapshot taken {stamp}; seats are as of that date, not live. Verify in TUportal before registering.")
    add("registration_restrictions", False, "warning", "Major, class-level, permit and hold restrictions are not in the snapshot; TUportal enforces them at registration.")
    add("requirement_provenance", False, "warning", "Requirements were parsed automatically from the Academic Bulletin and are pending verification against your official degree audit.")
    f1 = f1_assessment(sections, courses, s.f1_status)
    if f1.applies:
        sev = {"meets": "info", "needs_confirmation": "warning", "below": "error"}[f1.status]
        add("f1_full_course_of_study", f1.status == "meets", sev,
            f"{f1.credits_toward_full_time:g}/{f1.full_time_required} credits count toward full course of study "
            f"({f1.online_credits_counted:g} of {f1.online_credits:g} online credits counted). " + " ".join(f1.notes)
            + " Planning assistance only; not immigration advice.")
    return checks


class AcademicReviewAgent(Agent):
    key = "academic_review"
    title = "Academic Review Agent"
    responsibility = "Independently re-verifies every option with deterministic checks and can reject a schedule."

    def run(self, ctx: PlanContext) -> dict:
        opt_out = ctx.state["schedule_optimization"]
        reviews, rejected = {}, []
        for opt in opt_out["options"]:
            secs = [SectionData(**{k: v for k, v in x.items() if k in SectionData.model_fields}) for x in opt["sections"]]
            checks = review_sections(ctx, secs, {x["course"]: x["requirement_ids"] for x in opt["sections"]},
                                     components_by_course(ctx.catalog.sections),
                                     {c["course"] for c in ctx.state.get("interest_matching", {}).get("interest_electives", [])})
            errors = [c for c in checks if not c["passed"] and c["severity"] == "error"]
            warnings = [c for c in checks if not c["passed"] and c["severity"] == "warning"]
            status = "rejected" if errors else ("checks_passed_with_warnings" if warnings else "checks_passed")
            reviews[opt["id"]] = {"status": status, "checks": checks, "errors": len(errors), "warnings": len(warnings),
                                  "data_verified": False}
            if errors:
                rejected.append(opt["id"])
                # graduation-plan mode fixes the courses, so the re-optimization avoids the rejected sections instead
                plan_mode = ctx.state.get("schedule_optimization", {}).get("grad_plan_mode")
                ctx.state.setdefault("_review_rejected_sets", []).append(sorted(x["id" if plan_mode else "course"] for x in opt["sections"]))
                ctx.log(f"REJECTED {opt['label']}", errors=[e["detail"] for e in errors])
            else:
                ctx.log(f"{opt['label']}: deterministic checks passed ({len(warnings)} warning(s))")
            self._persist(ctx, opt, status, checks)
        return {"reviews": reviews, "rejected": rejected,
                "note": "Options are marked 'checks passed' only after deterministic verification. Data provenance is demo, so no option is shown as officially validated."}

    def _persist(self, ctx: PlanContext, opt: dict, status: str, checks: list[dict]) -> None:
        old = ctx.db.get(ScheduleOption, opt["id"])
        if old:
            ctx.db.query(ValidationResult).filter_by(option_id=opt["id"]).delete()
            ctx.db.delete(old)
            ctx.db.flush()
        row = ScheduleOption(id=opt["id"], plan_id=ctx.plan_id, label=opt["label"], strategy=opt["strategy"], rank=opt["rank"],
                             total_credits=opt["credits"], scores=opt["scores"], violated_soft=opt["soft_violations"], review_status=status)
        row.courses = [ScheduleCourse(section_id=x["id"], course_code=x["course"], requirement_ids=x["requirement_ids"],
                                      interest_score=x["interest_score"], evidence={"prereq_status": x["prereq_status"], "data_source": x["data_source"]})
                       for x in opt["sections"]]
        ctx.db.add(row)
        ctx.db.flush()
        for c in checks:
            ctx.db.add(ValidationResult(option_id=opt["id"], check=c["check"], passed=c["passed"], severity=c["severity"], detail=c["detail"]))

    def decision(self, ctx, o):
        labels = {x["id"]: x["label"] for x in ctx.state["schedule_optimization"]["options"]}
        return {"task": "Independently re-verify each option with deterministic checks",
                "data_sources": ["Rules engine (not optimizer state)", "Class-search snapshot", "Bulletin prerequisites"],
                "findings": [f"{labels.get(k, k)}: {v['status'].replace('_', ' ')} ({v['errors']} error(s), {v['warnings']} warning(s))" for k, v in o["reviews"].items()],
                "recommendation": "Reject any option with an error; show warnings to the student.",
                "validation": {"status": "failed" if o["rejected"] else "passed", "detail": f"{len(o['rejected'])} option(s) rejected"},
                "unresolved": sorted({c["detail"][:120] for v in o["reviews"].values() for c in v["checks"] if not c["passed"] and c["severity"] == "warning"})[:5]}

    def summarize(self, o: dict) -> str:
        return f"Reviewed {len(o['reviews'])} option(s); {len(o['rejected'])} rejected."
