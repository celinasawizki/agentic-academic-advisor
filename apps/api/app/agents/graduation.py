from functools import lru_cache

from app.agents.base import Agent, PlanContext

TYPE_WEIGHT = {"major": 0.15, "minor": 0.05, "certificate": 0.05, "gened": 0.0, "school": 0.1, "university": 0.1}


def term_index(term: str) -> int:
    """Banner term codes: YYYY03 spring, YYYY20/26 summer, YYYY36 fall. Legacy 'YYYY-SP'/'YYYY-FA' also accepted."""
    if "-" in term:
        year, season = term.split("-")
        return int(year) * 2 + (0 if season.upper() == "SP" else 1)
    year, part = int(term[:4]), term[4:]
    return year * 2 + (1 if part == "36" else 0)


def semesters_remaining(planning_term: str, expected_graduation: str) -> int:
    """Fall/spring terms from the planning term through graduation (inclusive)."""
    gy, gm = (int(p) for p in expected_graduation.split("-"))
    end = gy * 2 + (0 if gm <= 6 else 1)
    return max(0, end - term_index(planning_term) + 1)


class GraduationPlanningAgent(Agent):
    key = "graduation_planning"
    title = "Graduation Planning Agent"
    responsibility = "Evaluates prerequisite chains, bottlenecks and term-by-term feasibility of the target graduation date."

    def run(self, ctx: PlanContext) -> dict:
        s = ctx.student
        req = ctx.state["degree_requirements"]
        disc = ctx.state["course_discovery"]
        courses = ctx.catalog.courses
        remaining_courses: dict[str, dict] = {}
        for r in req["remaining"]:
            mandatory = r["kind"] == "count" and len(r["options"]) == 1 and not r["patterns"]
            codes = set(r["candidate_courses"]) | {e["course"] for e in disc["eligible_sections"] if r["id"] in e["requirement_ids"]}
            for c in codes:
                meta = remaining_courses.setdefault(c, {"requirements": [], "mandatory": False, "program_type": r["program_type"],
                                                        "patterned": bool(r["patterns"]) and c not in r["candidate_courses"]})
                meta["requirements"].append(r["id"])
                meta["mandatory"] |= mandatory
                if TYPE_WEIGHT.get(r["program_type"], 0) > TYPE_WEIGHT.get(meta["program_type"], 0):
                    meta["program_type"] = r["program_type"]

        downstream: dict[str, set[str]] = {c: set() for c in remaining_courses}
        for c in remaining_courses:
            for group in courses[c].prereqs if c in courses else []:
                for p in group:
                    if p in downstream and p != c:
                        downstream[p].add(c)

        @lru_cache(maxsize=None)
        def chain(c: str, depth: int = 0) -> int:
            if depth > 8:
                return 1
            return 1 + max((chain(d, depth + 1) for d in downstream.get(c, ())), default=0)

        sem_left = semesters_remaining(s.planning_term, s.expected_graduation)
        priorities, critical = {}, []
        for c, meta in remaining_courses.items():
            p = (0.6 if meta["mandatory"] else 0.3 if meta["patterned"] else 0.45) + TYPE_WEIGHT.get(meta["program_type"], 0)
            p += min(0.15, 0.03 * len(meta["requirements"]))
            unlocks = sorted(downstream[c])
            p += min(0.2, 0.05 * len(unlocks))
            ch = chain(c)
            slack = sem_left - ch
            if meta["mandatory"] and ch >= 2 and slack <= 1:
                p += 0.2
                critical.append({"course": c, "chain_length": ch, "semesters_left": sem_left, "slack": slack, "unlocks": unlocks[:8],
                                 "reason": f"{c} starts a {ch}-course prerequisite chain with only {slack} semester(s) of slack before {s.expected_graduation}."})
            priorities[c] = {"priority": round(min(1.0, p), 3), "chain_length": ch, "unlocks": unlocks[:8], "mandatory": meta["mandatory"]}

        courses_needed = req["courses_needed"]
        per_term = courses_needed / max(1, sem_left)
        risks, assumptions = [], [
            "Assumes fall/spring enrollment only (no summer).",
            "Assumes future terms offer remaining courses; only the planning term's sections are in the snapshot.",
            "A course is graduation-critical when it is individually required and begins a prerequisite chain with ≤1 semester of slack.",
            "Requirement rules were parsed automatically from the bulletin and may not reflect approved substitutions or your degree audit.",
        ]
        if req.get("manual_review"):
            risks.append({"severity": "medium", "issue": f"{len(req['manual_review'])} requirement rule(s) could not be parsed and need manual review."})
        if per_term > 5.5:
            risks.append({"severity": "high", "issue": f"~{courses_needed} courses remain over {sem_left} semesters (~{per_term:.1f}/term)."})
        elif per_term > 5:
            risks.append({"severity": "medium", "issue": f"Heavy remaining load: ~{per_term:.1f} courses per term."})
        offered = {e["course"] for e in disc["eligible_sections"]}
        for c in critical:
            if c["course"] not in offered:
                risks.append({"severity": "high", "issue": f"Graduation-critical {c['course']} has no eligible section this term."})
        ctx.log(f"{sem_left} semesters remain through {s.expected_graduation}; ~{courses_needed} courses needed (~{per_term:.1f}/term)")
        if critical:
            ctx.log("Graduation-critical courses identified", courses=[c["course"] for c in critical])
        return {"semesters_remaining": sem_left, "courses_needed": courses_needed, "courses_per_term_needed": round(per_term, 2),
                "priorities": priorities, "critical_courses": critical, "risks": risks, "assumptions": assumptions,
                "on_track": not any(r["severity"] == "high" for r in risks)}

    def decision(self, ctx, o):
        return {"task": "Assess prerequisite sequencing and pace toward the target graduation date",
                "data_sources": ["Bulletin prerequisites", "Open requirement rules", "Student target graduation"],
                "findings": [self.summarize(o), *[c["reason"] for c in o["critical_courses"][:4]]],
                "recommendation": ("Prioritize " + ", ".join(c["course"] for c in o["critical_courses"]) + " this term.") if o["critical_courses"]
                else "No graduation-critical course this term.",
                "validation": {"status": "passed" if o["on_track"] else "warnings", "detail": "On track" if o["on_track"] else "High-severity risk detected"},
                "unresolved": [r["issue"] for r in o["risks"]] + o["assumptions"][:2]}

    def summarize(self, o: dict) -> str:
        crit = ", ".join(c["course"] for c in o["critical_courses"][:5]) or "none"
        return f"{o['semesters_remaining']} semesters left, ~{o['courses_per_term_needed']} courses/term needed. Critical: {crit}."
