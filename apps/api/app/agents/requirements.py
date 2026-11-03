from app.agents.base import Agent, PlanContext
from app.rules import requirement_progress


RELIABILITY = ("VERIFIED", "PENDING_VERIFICATION", "AMBIGUOUS", "UNAVAILABLE", "BLOCKED")


def reliability(p: dict, verified: dict[str, dict], year_mismatch: bool, year_assumed: bool) -> tuple[str, str]:
    """How much the planner can rely on a requirement rule. UNAVAILABLE/BLOCKED are applied later
    by Course Discovery from this term's sections. VERIFIED only comes from a human registry."""
    if p["kind"] == "manual":
        return "AMBIGUOUS", "Written as free text in the bulletin; the parser could not interpret it. An advisor must review it."
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
    title = "Degree Requirements Research Agent"
    responsibility = "Researches the ingested Academic Bulletin requirements for each program and computes what remains."

    def run(self, ctx: PlanContext) -> dict:
        s = ctx.student
        supported = [p for p in s.program_ids if ctx.catalog.programs.get(p, {}).get("supported")]
        reqs = [r for r in ctx.catalog.requirements if r.program_id in supported]
        for pid in supported:
            prog = ctx.catalog.programs[pid]
            ctx.cite("bulletin", f"{prog['name']} — Temple Academic Bulletin {prog['catalog_year'] or ''}".strip(),
                     prog.get("source_url"), prog.get("retrieved_at"), "parsed_pending_verification")
            n = sum(1 for r in reqs if r.program_id == pid)
            review = sum(1 for r in reqs if r.program_id == pid and r.verification_status == "needs_review")
            ctx.log(f"Loaded {n} requirement rules for {prog['name']}" + (f" ({review} need manual review)" if review else ""),
                    catalog_year=prog["catalog_year"])
        if s.catalog_year:
            for pid in supported:
                prog = ctx.catalog.programs[pid]
                if prog["catalog_year"] and prog["catalog_year"] != s.catalog_year:
                    ctx.log(f"{prog['name']}: only the {prog['catalog_year']} bulletin is available (you entered {s.catalog_year}). "
                            "Earlier bulletin years live in Temple's archives and were not ingested; confirm with your advisor.")

        progress = requirement_progress(reqs, s.transcript, ctx.catalog.double_count_allowed, ctx.catalog.courses)
        out = [p.to_dict() for p in progress]
        mismatch = {pid for pid in supported if s.catalog_year and ctx.catalog.programs[pid]["catalog_year"]
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
            "reliability_counts": {k: sum(1 for p in out if p["kind"] != "note" and p["reliability"] == k) for k in RELIABILITY},
            "double_counting_policy": "Courses are not double counted across programs unless an explicit rule allows it.",
            "review_flags": review_flags,
        }

    def summarize(self, o: dict) -> str:
        countable = [r for r in o["requirements"] if r["kind"] in ("count", "credits")]
        done = sum(1 for r in countable if r["status"] == "complete")
        manual = len(o["manual_review"])
        return (f"{done}/{len(countable)} requirement rules complete; ~{o['courses_needed']} more courses needed"
                + (f"; {manual} rule(s) need manual review." if manual else "."))
