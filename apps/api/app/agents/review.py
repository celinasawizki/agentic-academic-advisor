from app.agents.base import Agent, PlanContext
from app.domain import SectionData
from app.models import ScheduleCourse, ScheduleOption, ValidationResult
from app.rules import campus_supported, f1_assessment, overlapping_blocks, prereq_status, sections_conflict


def review_sections(ctx: PlanContext, sections: list[SectionData], requirement_ids: dict[str, list[str]]) -> list[dict]:
    """Independent re-verification. Deliberately does not reuse optimizer state."""
    s, p, courses = ctx.student, ctx.student.preferences, ctx.catalog.courses
    checks: list[dict] = []

    def add(check: str, passed: bool, severity: str, detail: str):
        checks.append({"check": check, "passed": passed, "severity": "info" if passed else severity, "detail": detail})

    codes = [x.course for x in sections]
    add("unique_courses", len(codes) == len(set(codes)), "error", "Each course appears once." if len(codes) == len(set(codes)) else "Duplicate course in schedule.")
    clashes = [(a.id, b.id) for i, a in enumerate(sections) for b in sections[i + 1:] if sections_conflict(a, b)]
    add("time_conflicts", not clashes, "error", "No overlapping meetings." if not clashes else f"Overlapping sections: {clashes}")
    hard_hits = [(x.course, b.label) for x in sections for b in overlapping_blocks(x, [b for b in s.availability if b.kind == "hard"])]
    add("hard_availability", not hard_hits, "error", "Respects all hard availability blocks." if not hard_hits else f"Violates hard availability: {hard_hits}")
    total = sum(courses[x.course].credits for x in sections)
    add("credit_range", p.credit_min <= total <= p.credit_max, "error", f"{total} credits (allowed {p.credit_min}-{p.credit_max}).")
    for x in sections:
        pre = prereq_status(courses[x.course], s.transcript)
        if pre.status == "missing":
            add(f"prereq:{x.course}", False, "error", f"{x.course} prerequisite not met.")
        elif pre.status == "conditional":
            add(f"prereq:{x.course}", False, "warning", f"{x.course} depends on in-progress {', '.join(pre.pending_courses)}; enrollment is conditional on passing.")
        if not campus_supported(x):
            add(f"campus:{x.course}", False, "error", f"{x.id} is at unsupported campus {x.campus}.")
        if x.term_id != ctx.catalog.term_id:
            add(f"term:{x.course}", False, "error", f"{x.id} is not in {ctx.catalog.term_name}.")
        if not requirement_ids.get(x.course):
            add(f"requirement:{x.course}", False, "warning", f"{x.course} is not linked to a remaining requirement.")
    if any(x.data_source != "verified" for x in sections):
        add("section_provenance", False, "warning", "Section times come from a labeled demo fixture, not live Temple course search. Verify in Self-Service Banner before registering.")
    if any(r["verification_status"] != "verified" for r in ctx.state["degree_requirements"]["requirements"]):
        add("requirement_provenance", False, "warning", "Requirement data is a demo fixture pending verification against the official bulletin / degree audit.")
    f1 = f1_assessment(sections, courses, s.f1_status)
    if f1.applies:
        sev = {"meets": "info", "needs_confirmation": "warning", "below": "error"}[f1.status]
        add("f1_full_course_of_study", f1.status == "meets", sev,
            f"{f1.credits_toward_full_time}/{f1.full_time_required} credits count toward full course of study. " + " ".join(f1.notes)
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
            checks = review_sections(ctx, secs, {x["course"]: x["requirement_ids"] for x in opt["sections"]})
            errors = [c for c in checks if not c["passed"] and c["severity"] == "error"]
            warnings = [c for c in checks if not c["passed"] and c["severity"] == "warning"]
            status = "rejected" if errors else ("checks_passed_with_warnings" if warnings else "checks_passed")
            reviews[opt["id"]] = {"status": status, "checks": checks, "errors": len(errors), "warnings": len(warnings),
                                  "data_verified": False}
            if errors:
                rejected.append(opt["id"])
                ctx.state.setdefault("_review_rejected_sets", []).append(sorted(x["course"] for x in opt["sections"]))
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

    def summarize(self, o: dict) -> str:
        return f"Reviewed {len(o['reviews'])} option(s); {len(o['rejected'])} rejected."
