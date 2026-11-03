from app.agents.base import Agent, PlanContext
from app.rules import COMPLETED_STATUSES


class AcademicProfileAgent(Agent):
    key = "academic_profile"
    title = "Academic Profile Agent"
    responsibility = "Interprets transcript and degree-audit records, separates completed from in-progress work, and resolves catalog year."

    def run(self, ctx: PlanContext) -> dict:
        s = ctx.student
        courses = ctx.catalog.courses
        buckets: dict[str, list[dict]] = {k: [] for k in ("completed", "transfer", "in_progress", "planned", "unverified")}
        warnings = []
        for t in s.transcript:
            known = t.course in courses
            entry = {"course": t.course, "title": courses[t.course].title if known else None,
                     "credits": courses[t.course].credits if known else None, "grade": t.grade,
                     "term": t.term, "source": t.source, "confidence": t.confidence}
            if not known:
                warnings.append(f"{t.course} is not in the course dataset; it cannot be applied to requirements until verified.")
            if t.confidence < 0.8:
                warnings.append(f"{t.course} was extracted with low confidence ({t.confidence:.0%}); please confirm it.")
            buckets[t.status].append(entry)
            if t.source == "degree_audit_pdf":
                ctx.cite("degree_audit_upload", "Student-uploaded degree audit (parsed locally)", verification_status="student_verified")

        earned = sum(e["credits"] or 0 for k in COMPLETED_STATUSES for e in buckets[k])
        in_prog = sum(e["credits"] or 0 for e in buckets["in_progress"])
        ctx.log("Classified transcript entries", **{k: len(v) for k, v in buckets.items()})
        if buckets["in_progress"]:
            ctx.log("In-progress courses are not treated as completed; prerequisites that depend on them are conditional.",
                    courses=[e["course"] for e in buckets["in_progress"]])

        program_years = {ctx.catalog.programs[p]["catalog_year"] for p in s.program_ids if p in ctx.catalog.programs}
        catalog_year = s.catalog_year or (sorted(y for y in program_years if y)[-1] if program_years else None)
        if not s.catalog_year:
            warnings.append(f"Catalog year not provided; assumed {catalog_year} from program data. Confirm with your advisor.")
        unsupported = [ctx.catalog.programs[p]["name"] for p in s.program_ids
                       if p in ctx.catalog.programs and not ctx.catalog.programs[p]["supported"]]
        for name in unsupported:
            warnings.append(f"{name} is not yet supported by verified requirement data and was skipped.")

        return {
            "student_id": s.id, "academic_year": s.academic_year, "expected_graduation": s.expected_graduation,
            "catalog_year": catalog_year, "catalog_year_source": "student" if s.catalog_year else "assumed",
            "programs": [{"id": p, "name": ctx.catalog.programs[p]["name"], "type": ctx.catalog.programs[p]["type"],
                          "supported": ctx.catalog.programs[p]["supported"]} for p in s.program_ids if p in ctx.catalog.programs],
            "courses": buckets, "earned_credits": earned, "in_progress_credits": in_prog,
            "f1_status": s.f1_status, "campus": s.campus, "warnings": warnings,
        }

    def summarize(self, o: dict) -> str:
        c = o["courses"]
        return (f"{len(c['completed']) + len(c['transfer'])} completed/transfer courses ({o['earned_credits']} credits), "
                f"{len(c['in_progress'])} in progress. Catalog year {o['catalog_year']} ({o['catalog_year_source']}).")
