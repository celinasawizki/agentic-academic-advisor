from app.agents.base import Agent, PlanContext
from app.rules import requirement_progress


class DegreeRequirementsAgent(Agent):
    key = "degree_requirements"
    title = "Degree Requirements Research Agent"
    responsibility = "Researches the ingested program requirements for the student's catalog year and computes what remains."

    def run(self, ctx: PlanContext) -> dict:
        s = ctx.student
        supported = [p for p in s.program_ids if ctx.catalog.programs.get(p, {}).get("supported")]
        reqs = [r for r in ctx.catalog.requirements if r.program_id in supported]
        for pid in supported:
            prog = ctx.catalog.programs[pid]
            ctx.cite("bulletin", f"{prog['name']} ({prog['type']}) requirements, catalog {prog['catalog_year']} — ingested demo fixture",
                     prog.get("source_url"), prog.get("retrieved_at"), "demo_unverified")
            ctx.log(f"Loaded {sum(1 for r in reqs if r.program_id == pid)} requirement groups for {prog['name']}",
                    catalog_year=prog["catalog_year"])
        if s.catalog_year:
            mismatched = [ctx.catalog.programs[p]["name"] for p in supported if ctx.catalog.programs[p]["catalog_year"] != s.catalog_year]
            for name in mismatched:
                ctx.log(f"Requirements for {name} are only available for a different catalog year; flagged for review.")

        progress = requirement_progress(reqs, s.transcript, ctx.catalog.double_count_allowed)
        out = [p.to_dict() for p in progress]
        review_flags = []
        for p in out:
            if p["verification_status"] != "verified":
                review_flags.append({"requirement": p["id"], "issue": "Requirement data is a demo fixture and has not been verified against the official bulletin."})
            for n in p["notes"]:
                review_flags.append({"requirement": p["id"], "issue": n})
        remaining = [p for p in out if p["remaining_needed"] > 0]
        ctx.log(f"{len(remaining)} requirement groups still need courses",
                remaining={p["id"]: p["remaining_needed"] for p in remaining})
        return {
            "requirements": out,
            "remaining": remaining,
            "courses_needed": sum(p["remaining_needed"] for p in remaining),
            "double_counting_policy": "Courses are not double counted across programs unless an explicit rule allows it.",
            "review_flags": review_flags,
        }

    def summarize(self, o: dict) -> str:
        done = sum(1 for r in o["requirements"] if r["status"] == "complete")
        return f"{done}/{len(o['requirements'])} requirement groups complete; {o['courses_needed']} more courses needed across {len(o['remaining'])} groups."
