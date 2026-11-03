from app.agents.base import Agent, PlanContext
from app.agents.research import effective_program_ids
from app.rules import LAYER_TYPES, requirement_progress


RELIABILITY = ("VERIFIED", "PENDING_VERIFICATION", "AMBIGUOUS", "UNAVAILABLE", "BLOCKED")


def reliability(p: dict, verified: dict[str, dict], year_mismatch: bool, year_assumed: bool) -> tuple[str, str]:
    """How much the planner can rely on a requirement rule. UNAVAILABLE/BLOCKED are applied later
    by Course Discovery from this term's sections. VERIFIED only comes from a human registry."""
    if p["kind"] == "manual":
        return "AMBIGUOUS", "Written as free text in the bulletin; the parser could not interpret it. An advisor must review it."
    if p.get("evidence") and p["verification_status"] == "needs_review":
        return "AMBIGUOUS", "The bulletin sentence this rule was transcribed from was not found on the current page, or the page doesn't list the exact courses."
    if p["verification_status"] == "needs_review":
        return "AMBIGUOUS", "Parsed from prose or an unusual table layout; needs advisor review."
    if year_mismatch:
        return "AMBIGUOUS", "Your catalog year differs from the ingested bulletin year; requirements may differ."
    if p["id"] in verified:
        v = verified[p["id"]]
        return "VERIFIED", f"Verified by {v['verified_by']} on {v.get('verified_at', '?')} against {v['evidence']}."
    note = " Catalog year was assumed." if year_assumed else ""
    return "PENDING_VERIFICATION", "Parsed automatically from the Academic Bulletin; not yet checked against your official degree audit." + note


class DegreeRequirementsAgent(Agent):
    key = "degree_requirements"
    title = "Degree Requirements Agent"
    responsibility = "Applies program, school and university requirements from the bulletin to the record and computes what remains."

    def run(self, ctx: PlanContext) -> dict:
        s = ctx.student
        research = ctx.state.get("requirements_research") or {}
        effective = research.get("effective_programs") or effective_program_ids(s.program_ids, ctx.catalog.programs)
        supported = [p for p in effective if ctx.catalog.programs.get(p, {}).get("supported")]
        reqs = [r for r in ctx.catalog.requirements if r.program_id in supported]
        for pid in supported:
            prog = ctx.catalog.programs[pid]
            ctx.cite("bulletin", f"{prog['name']} — Temple Academic Bulletin {prog.get('catalog_year') or ''}".strip(),
                     prog.get("source_url"), prog.get("retrieved_at"), "parsed_pending_verification")
            n = sum(1 for r in reqs if r.program_id == pid)
            review = sum(1 for r in reqs if r.program_id == pid and r.verification_status == "needs_review")
            layer = " (applies automatically)" if prog["type"] in LAYER_TYPES else ""
            ctx.log(f"Loaded {n} requirement rules for {prog['name']}{layer}" + (f" ({review} need manual review)" if review else ""),
                    catalog_year=prog.get("catalog_year"))
        if s.catalog_year:
            for pid in supported:
                prog = ctx.catalog.programs[pid]
                if prog.get("catalog_year") and prog["catalog_year"] != s.catalog_year:
                    ctx.log(f"{prog['name']}: only the {prog['catalog_year']} bulletin is available (you entered {s.catalog_year}). "
                            "Earlier bulletin years live in Temple's archives and were not ingested; confirm with your advisor.")

        progress = requirement_progress(reqs, s.transcript, ctx.catalog.double_count_allowed, ctx.catalog.courses)
        out = [p.to_dict() for p in progress]
        mismatch = {pid for pid in supported if s.catalog_year and ctx.catalog.programs[pid].get("catalog_year")
                    and ctx.catalog.programs[pid]["catalog_year"] != s.catalog_year}
        for p in out:
            p["reliability"], p["reliability_reason"] = reliability(p, ctx.catalog.verified_rules, p["program_id"] in mismatch,
                                                                    s.catalog_year is None)
        review_flags = []
        for p in out:
            if p["verification_status"] == "needs_review" or p["kind"] == "manual":
                review_flags.append({"requirement": p["id"], "issue": f"Needs manual review: {p['name']}"})
            for n in p["notes"]:
                review_flags.append({"requirement": p["id"], "issue": n})
        remaining = [p for p in out if p["kind"] in ("count", "credits") and p["remaining_needed"] > 0]
        ctx.log(f"{len(remaining)} requirement rules still need courses",
                remaining={p["id"]: p["remaining_needed"] for p in remaining[:40]})
        return {
            "requirements": out,
            "remaining": remaining,
            "courses_needed": sum(p["remaining_courses"] for p in remaining),
            "manual_review": [p for p in out if p["kind"] == "manual"],
            "reliability_counts": {k: sum(1 for p in out if p["kind"] not in ("note", "policy") and p["reliability"] == k) for k in RELIABILITY},
            "layers": [{"id": pid, "name": ctx.catalog.programs[pid]["name"], "type": ctx.catalog.programs[pid]["type"],
                        "source_url": ctx.catalog.programs[pid].get("source_url")} for pid in supported
                       if ctx.catalog.programs[pid]["type"] in LAYER_TYPES],
            "milestones": [p for p in out if p["kind"] == "milestone"],
            "policies": [p for p in out if p["kind"] == "policy"],
            "double_counting_policy": "Courses are not double counted across programs unless an explicit rule allows it.",
            "review_flags": review_flags,
        }

    def decision(self, ctx, o):
        rc = o.get("reliability_counts", {})
        return {"task": "Apply each program's bulletin rules to the record and compute what remains",
                "data_sources": [f"Temple Academic Bulletin — {ctx.catalog.programs[p]['name']}" for p in ctx.student.program_ids if p in ctx.catalog.programs],
                "findings": [self.summarize(o), "Reliability: " + ", ".join(f"{k.replace('_', ' ').lower()} {v}" for k, v in rc.items() if v)],
                "recommendation": f"Plan toward {len(o['remaining'])} open rules; do not double count across programs without an explicit rule.",
                "validation": {"status": "warnings" if o["manual_review"] else "passed",
                               "detail": "No rule is advisor-verified yet" if not rc.get("VERIFIED") else f"{rc['VERIFIED']} verified rule(s)"},
                "unresolved": [f"Manual review: {r['program_name']} — {r['name'][:90]}" for r in o["manual_review"][:6]]}

    def summarize(self, o: dict) -> str:
        countable = [r for r in o["requirements"] if r["kind"] in ("count", "credits", "milestone")]
        done = sum(1 for r in countable if r["status"] == "complete")
        manual = len(o["manual_review"])
        layers = len(o.get("layers", []))
        return (f"{done}/{len(countable)} requirement rules complete (incl. {layers} school/university layer(s)); "
                f"~{o['courses_needed']} more courses needed" + (f"; {manual} rule(s) need manual review." if manual else "."))
