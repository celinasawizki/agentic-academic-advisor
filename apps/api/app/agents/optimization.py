from app.agents.base import Agent, PlanContext
from app.domain import AvailBlock, SectionData
from app.optimizer import STRATEGIES, Candidate, HardGroup, ScheduleModel, Strategy
from app.rules import f1_assessment, overlapping_blocks, section_credits

PREF_PREFIX = "Preference: "


MAX_COURSES = 45
MAX_SECTIONS_PER_COURSE = 6


def build_model(ctx: PlanContext, blocks: list[AvailBlock] | None = None) -> ScheduleModel:
    """Builds the CP-SAT model over a pruned candidate set: the highest-value
    courses (degree priority + interest) plus anything the student or the
    graduation plan requires, with a few sections each."""
    disc = ctx.state["course_discovery"]
    grad = ctx.state["graduation_planning"]
    interest = ctx.state["interest_matching"]["scores"]
    cons = ctx.state["scheduling_constraints"]
    prefs = ctx.student.preferences
    blocks = blocks if blocks is not None else ctx.student.availability
    hard = [b for b in blocks if b.kind == "hard"]
    soft = [b for b in blocks if b.kind == "soft"]
    critical = [c for c in cons["must_courses_graduation_strategy"] if c not in prefs.required_courses]
    locked_courses = {e["course"] for e in disc["eligible_sections"] if e["section"]["id"] in prefs.locked_sections}
    keep_always = set(critical) | set(prefs.required_courses) | locked_courses

    def value(code: str) -> float:
        return grad["priorities"].get(code, {}).get("priority", 0.3) + interest.get(code, {}).get("score", 0.0)

    by_course: dict[str, list[dict]] = {}
    for e in disc["eligible_sections"]:
        by_course.setdefault(e["course"], []).append(e)
    ranked = sorted(by_course, key=lambda c: -value(c))
    chosen_courses = list(dict.fromkeys([c for c in ranked if c in keep_always] + ranked[:MAX_COURSES]))

    candidates = []
    for code in chosen_courses:
        entries = by_course[code]
        secs = [(SectionData(**e["section"]), e) for e in entries]
        secs.sort(key=lambda se: (se[0].id not in prefs.locked_sections, bool(overlapping_blocks(se[0], hard)),
                                  len(overlapping_blocks(se[0], soft)), se[1].get("time_tba", False)))
        per_comp: dict[str, int] = {}
        for sec, e in secs:
            per_comp[sec.component] = per_comp.get(sec.component, 0) + 1
            if per_comp[sec.component] > MAX_SECTIONS_PER_COURSE:
                continue
            candidates.append(Candidate(section=sec, credits=section_credits(sec, ctx.catalog.courses),
                                        requirement_ids=e["requirement_ids"],
                                        priority=grad["priorities"].get(code, {}).get("priority", 0.3),
                                        interest=interest.get(code, {}).get("score", 0.0)))
    # Each option counts once toward a requirement: the first course of a bundle (e.g. lecture & lab
    # pair) carries the weight, its partners count zero; pattern matches count one each.
    caps = {}
    for r in ctx.state["degree_requirements"]["remaining"]:
        weights: dict[str, int] = {}
        for opt in r["options"]:
            for i, c in enumerate(opt):
                weights[c] = max(weights.get(c, 0), 1 if i == 0 else 0)
        caps[r["id"]] = (max(1, r["remaining_courses"]), weights)
    return ScheduleModel(candidates, ctx.catalog.courses, blocks, prefs, caps, ctx.student.f1_status == "yes", critical,
                         student_required=prefs.required_courses)


def describe_resolution(ctx: PlanContext, g: HardGroup, res) -> dict:
    grad = ctx.state["graduation_planning"]
    out = {"relaxes": g.key, "feasible": res.feasible, "credits": res.credits,
           "sections": [s.id for s in res.sections], "courses": [s.course for s in res.sections]}
    if g.kind == "availability" and g.description.startswith(f"Unavailable: {PREF_PREFIX}"):
        label = g.description.removeprefix(f"Unavailable: {PREF_PREFIX}")
        hits = [s.course for s in res.sections if any(b.label == label for b in ctx.student.availability
                                                       if b.kind == "soft" and _overlaps(s, b))]
        out.update(type="relax_soft", constraint_class="soft",
                   title=f"Give up '{label}' for this term",
                   detail=f"Take {', '.join(hits) or 'the conflicting course'} during your '{label}' time and stay on track.",
                   requires="your informed approval")
    elif g.kind == "availability":
        label = g.description.removeprefix("Unavailable: ")
        out.update(type="change_hard", constraint_class="hard",
                   title=f"Change your hard availability: {label}",
                   detail="This is a hard constraint; the planner will never schedule over it automatically.",
                   requires="explicit change to your availability")
    elif g.kind in ("must_course", "student_required"):
        course = g.key.split(":", 1)[1]
        crit = next((c for c in grad["critical_courses"] if c["course"] == course), None)
        alts = _alternatives(ctx, course)
        out.update(type="defer_course", constraint_class="academic_priority",
                   title=f"Defer {course} to a future term",
                   detail=(f"Keeps all your preferences. Risk: {crit['reason']} Deferring uses that slack, subject to future availability."
                           if crit else f"{course} would be taken in a later term, subject to availability."),
                   alternatives=alts,
                   alternative_note=("Approved alternatives in the same requirement: " + ", ".join(alts)) if alts
                   else f"No approved alternative course for {course} exists in the requirement data (it is a required course).",
                   requires="your decision; check with your advisor")
    elif g.kind == "credit_min":
        f1 = ctx.student.f1_status == "yes"
        out.update(type="reduce_credits", constraint_class="soft",
                   title=f"Reduce credit load to {res.credits}",
                   detail=("Dropping below 12 credits as an F-1 student requires an approved Reduced Course Load from ISSS." if f1 and res.credits < 12
                           else f"A valid schedule exists at {res.credits} credits."),
                   requires="your approval" + (" and ISSS authorization" if f1 and res.credits < 12 else ""))
    elif g.kind == "f1_full_time":
        out.update(type="not_overridable", constraint_class="immigration", feasible=False,
                   title="F-1 full course of study", detail="Immigration requirements cannot be overridden by preference settings. Contact ISSS.",
                   requires="ISSS")
    else:
        out.update(type="other", constraint_class="hard", title=f"Relax: {g.description}", detail="", requires="your approval")
    return out


def _overlaps(s: SectionData, b: AvailBlock) -> bool:
    return bool(overlapping_blocks(s, [b]))


def _alternatives(ctx: PlanContext, course: str) -> list[str]:
    alts = []
    for r in ctx.state["degree_requirements"]["remaining"]:
        if r["kind"] in ("count", "credits") and any(course in o for o in r["options"]) and len(r["options"]) > 1:
            alts += [o[0] for o in r["options"] if course not in o and o[0] in r["candidate_courses"]]
    return sorted(set(alts))[:8]


class ScheduleOptimizationAgent(Agent):
    key = "schedule_optimization"
    title = "Schedule Optimization Agent"
    responsibility = "Runs the OR-Tools CP-SAT model for three strategies and analyzes infeasibility with solver-computed conflict sets."

    def run(self, ctx: PlanContext) -> dict:
        model = build_model(ctx)
        excluded_sets: list[set[str]] = [set(x) for x in ctx.state.get("_review_rejected_sets", [])]
        options, infeasible = [], []
        for rank, strat in enumerate(STRATEGIES, start=1):
            res = model.solve(strat, exclude_sets=excluded_sets)
            if not res.feasible:
                ctx.log(f"{strat.label}: infeasible", conflict_set=[g.description for g in res.conflict_set])
                infeasible.append({"strategy": strat.key, "label": strat.label,
                                   "conflict_set": [g.__dict__ for g in res.conflict_set], "minimal": res.conflict_set_minimal,
                                   "resolutions": [describe_resolution(ctx, g, model.solve(strat, exclude_sets=excluded_sets, disabled={g.key}))
                                                   for g in res.conflict_set]})
                continue
            excluded_sets.append({s.course for s in res.sections})
            options.append(self._option(ctx, strat, rank, res, model))
            ctx.log(f"{strat.label}: {res.credits} credits, {len(res.sections)} courses, {len(res.soft_violations)} preference violation(s)",
                    courses=[s.course for s in res.sections], solver_status=res.breakdown.get("status"))

        ideal = self._ideal_analysis(ctx)
        return {"options": options, "infeasible_strategies": infeasible, "ideal_analysis": ideal,
                "solver": "Google OR-Tools CP-SAT", "strategies": [s.__dict__ for s in STRATEGIES]}

    def _option(self, ctx: PlanContext, strat: Strategy, rank: int, res, model: ScheduleModel) -> dict:
        disc = ctx.state["course_discovery"]
        interest = ctx.state["interest_matching"]["scores"]
        grad = ctx.state["graduation_planning"]
        by_section = {e["section"]["id"]: e for e in disc["eligible_sections"]}
        soft_count = max(1, sum(1 for b in ctx.student.availability if b.kind == "soft") + bool(ctx.student.preferences.avoid_before))
        violated_prefs = {v["preference"] for v in res.soft_violations}
        critical = [c["course"] for c in grad["critical_courses"]]
        chosen = {s.course for s in res.sections}
        return {
            "id": f"{ctx.plan_id}-{strat.key}",
            "strategy": strat.key, "label": strat.label, "rank": rank, "credits": res.credits,
            "sections": [{**s.model_dump(), "title": ctx.catalog.courses[s.course].title if s.course in ctx.catalog.courses else s.course,
                          "credits": section_credits(s, ctx.catalog.courses),
                          "requires_linked_section": by_section[s.id].get("requires_linked_section", False),
                          "time_tba": by_section[s.id].get("time_tba", False),
                          "requirement_ids": by_section[s.id]["requirement_ids"],
                          "prereq_status": by_section[s.id]["prereq_status"],
                          "prereq_pending": by_section[s.id]["prereq_pending"],
                          "interest_score": interest.get(s.course, {}).get("score", 0),
                          "priority": grad["priorities"].get(s.course, {}).get("priority", 0)} for s in res.sections],
            "scores": {**res.breakdown,
                       "preference_satisfaction": round(1 - len(violated_prefs) / soft_count, 2),
                       "objective": res.objective},
            "soft_violations": res.soft_violations,
            "critical_included": [c for c in critical if c in chosen],
            "critical_missing": [c for c in critical if c not in chosen],
            "f1": f1_assessment(res.sections, ctx.catalog.courses, ctx.student.f1_status).to_dict(),
        }

    def _ideal_analysis(self, ctx: PlanContext) -> dict:
        """Can every hard + soft availability preference AND every graduation-critical
        course be satisfied at once? Soft blocks are temporarily made hard so CP-SAT
        can return the irreducible set of constraints that conflict."""
        soft = [b for b in ctx.student.availability if b.kind == "soft"]
        if not soft and not ctx.state["scheduling_constraints"]["must_courses_graduation_strategy"]:
            return {"perfect_exists": True, "conflict_set": [], "resolutions": []}
        blocks = [b if b.kind == "hard" else AvailBlock(day=b.day, start=b.start, end=b.end, kind="hard", label=PREF_PREFIX + b.label)
                  for b in ctx.student.availability]
        model = build_model(ctx, blocks)
        strat = STRATEGIES[0]
        res = model.solve(strat)
        if res.feasible:
            ctx.log("A schedule satisfying every preference and graduation-critical course exists")
            return {"perfect_exists": True, "conflict_set": [], "resolutions": []}
        resolutions = [describe_resolution(ctx, g, model.solve(strat, disabled={g.key})) for g in res.conflict_set]
        ctx.log("No schedule satisfies all preferences; CP-SAT irreducible conflict set computed",
                conflict_set=[g.description for g in res.conflict_set])
        return {"perfect_exists": False, "minimal": res.conflict_set_minimal,
                "conflict_set": [{**g.__dict__, "description": g.description.replace(f"Unavailable: {PREF_PREFIX}", "Preference: ")} for g in res.conflict_set],
                "resolutions": resolutions}

    def summarize(self, o: dict) -> str:
        msg = f"{len(o['options'])} schedule option(s) generated with CP-SAT"
        if o["infeasible_strategies"]:
            msg += f"; {len(o['infeasible_strategies'])} strategy infeasible"
        if not o["ideal_analysis"]["perfect_exists"]:
            msg += "; no schedule satisfies every preference (conflict set computed)"
        return msg + "."
