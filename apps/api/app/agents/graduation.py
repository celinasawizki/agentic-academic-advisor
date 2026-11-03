from functools import lru_cache

from app.agents.base import Agent, PlanContext

CATEGORY_WEIGHT = {"core": 0.6, "capstone": 0.55, "elective": 0.4, "gened": 0.3}


def semesters_remaining(planning_term: str, expected_graduation: str) -> int:
    """Count fall/spring terms from the planning term through graduation (inclusive)."""
    year, season = planning_term.split("-")
    start = int(year) * 2 + (0 if season.upper() == "SP" else 1)
    gy, gm = (int(p) for p in expected_graduation.split("-"))
    end = gy * 2 + (0 if gm <= 6 else 1)
    return max(0, end - start + 1)


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
            for c in r["candidate_courses"]:
                remaining_courses.setdefault(c, {"requirements": [], "category": r["category"], "rule": r["rule"]})
                remaining_courses[c]["requirements"].append(r["id"])

        # Downstream: which remaining courses list c as a prerequisite.
        downstream: dict[str, set[str]] = {c: set() for c in remaining_courses}
        for c in remaining_courses:
            for group in courses[c].prereqs if c in courses else []:
                for p in group:
                    if p in downstream:
                        downstream[p].add(c)

        @lru_cache(maxsize=None)
        def chain(c: str) -> int:
            return 1 + max((chain(d) for d in downstream.get(c, ())), default=0)

        sem_left = semesters_remaining(s.planning_term, s.expected_graduation)
        priorities, critical = {}, []
        for c, meta in remaining_courses.items():
            mandatory = meta["rule"] == "all"
            p = CATEGORY_WEIGHT.get(meta["category"], 0.3) + (0.15 if mandatory else 0)
            unlocks = len(downstream[c])
            p += min(0.2, 0.1 * unlocks)
            ch = chain(c)
            slack = sem_left - ch
            is_critical = mandatory and ch >= 2 and slack <= 1
            if is_critical:
                p += 0.2
                critical.append({"course": c, "chain_length": ch, "semesters_left": sem_left, "slack": slack,
                                 "unlocks": sorted(downstream[c]),
                                 "reason": f"{c} starts a {ch}-course prerequisite chain with only {slack} semester(s) of slack before {s.expected_graduation}."})
            priorities[c] = {"priority": round(min(1.0, p), 3), "chain_length": ch, "unlocks": sorted(downstream[c]), "mandatory": mandatory}

        courses_needed = req["courses_needed"]
        per_term = courses_needed / max(1, sem_left)
        risks, assumptions = [], [
            "Assumes fall/spring enrollment only (no summer).",
            "Assumes future terms offer remaining courses; only the planning term's sections are in the dataset.",
            "A course is graduation-critical when it begins a prerequisite chain with ≤1 semester of slack.",
        ]
        if per_term > 5:
            risks.append({"severity": "high", "issue": f"{courses_needed} courses remain over {sem_left} semesters (~{per_term:.1f}/term)."})
        elif per_term > 4:
            risks.append({"severity": "medium", "issue": f"Heavy remaining load: ~{per_term:.1f} courses per term."})
        offered = {e["course"] for e in disc["eligible_sections"]}
        for c in critical:
            if c["course"] not in offered:
                risks.append({"severity": "high", "issue": f"Graduation-critical {c['course']} has no eligible section this term."})
        ctx.log(f"{sem_left} semesters remain through {s.expected_graduation}; {courses_needed} courses needed (~{per_term:.1f}/term)")
        if critical:
            ctx.log("Graduation-critical courses identified", courses=[c["course"] for c in critical])
        return {"semesters_remaining": sem_left, "courses_needed": courses_needed, "courses_per_term_needed": round(per_term, 2),
                "priorities": priorities, "critical_courses": critical, "risks": risks, "assumptions": assumptions,
                "on_track": not any(r["severity"] == "high" for r in risks)}

    def summarize(self, o: dict) -> str:
        crit = ", ".join(c["course"] for c in o["critical_courses"]) or "none"
        return f"{o['semesters_remaining']} semesters left, ~{o['courses_per_term_needed']} courses/term needed. Critical: {crit}."
