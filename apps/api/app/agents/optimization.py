import re
import time

from app.agents.base import Agent, PlanContext
from app.agents.categories import all_eligible, classify
from app.domain import AvailBlock, SectionData
from app.optimizer import STRATEGIES, Candidate, HardGroup, ScheduleModel, Strategy
from app.rules import counts_as_done, f1_assessment, overlapping_blocks, section_credits

PREF_PREFIX = "Preference: "


MAX_COURSES = 45
MAX_SECTIONS_PER_COURSE = 6
PRUNE_SLACK = 3


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

    free_codes = {el["course"] for el in ctx.state["interest_matching"].get("interest_electives", [])}

    def priority(code: str) -> float:
        return 0.0 if code in free_codes else grad["priorities"].get(code, {}).get("priority", 0.3)

    def value(code: str) -> float:
        return priority(code) + interest.get(code, {}).get("score", 0.0)

    by_course: dict[str, list[dict]] = {}
    for e in all_eligible(ctx.state):
        by_course.setdefault(e["course"], []).append(e)
    ranked = sorted(by_course, key=lambda c: -value(c))
    # Cap-aware pruning: a rule that can use n more courses contributes at most n + SLACK
    # candidates, so one broad rule (e.g. 14 language options for one language slot) can't
    # crowd out the courses that other requirements need.
    need = {r["id"]: max(1, r["remaining_courses"]) for r in ctx.state["degree_requirements"]["remaining"]}
    picked: dict[str, int] = {}
    pruned: dict[str, str] = {}
    chosen_courses = [c for c in ranked if c in keep_always]
    for code in ranked:
        if code in chosen_courses:
            continue
        reqs = {r for e in by_course[code] for r in e["requirement_ids"]}
        if len(chosen_courses) >= MAX_COURSES + len(keep_always):
            pruned[code] = f"the optimizer considers at most {MAX_COURSES} courses per run and {len(chosen_courses)} scored higher"
            continue
        if not any(picked.get(r, 0) < need.get(r, 2) + PRUNE_SLACK for r in reqs):
            pruned[code] = (f"every requirement it counts toward already had more higher-scoring candidates than open slots "
                            f"(slots + {PRUNE_SLACK})")
            continue
        chosen_courses.append(code)
        for r in reqs:
            picked[r] = picked.get(r, 0) + 1

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
                                        priority=priority(code),
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
    model = ScheduleModel(candidates, ctx.catalog.courses, blocks, prefs, caps, ctx.student.f1_status == "yes", critical,
                          student_required=prefs.required_courses, sequence_pairs=sequence_pairs(ctx, chosen_courses))
    # Kept so every "why not this course?" answer can say whether the solver even saw the course.
    model.pool = {"values": {c: round(value(c), 3) for c in ranked}, "priority": {c: round(priority(c), 3) for c in ranked},
                  "interest": {c: round(interest.get(c, {}).get("score", 0.0), 3) for c in ranked},
                  "considered": set(chosen_courses), "pruned": pruned,
                  "requirements": {c: sorted({r for e in by_course[c] for r in e["requirement_ids"]}) for c in ranked},
                  "sections": {c: [SectionData(**e["section"]) for e in by_course[c]] for c in ranked}}
    return model


OBJECTIVE_TEXT = ("Each strategy maximizes  w_req × Σ degree priority + w_int × Σ interest score − w_soft × preference penalties "
                  "− w_dev × |credits − target|  over the selected sections. Degree progress outweighs interest, so interest only "
                  "chooses among courses that count toward a requirement; a course that satisfies no requirement is added only "
                  "when requirement courses can't reach your credit target. Subject to every hard constraint "
                  "(no time conflicts, unavailable times, credit range, prerequisites, one section per component, "
                  "requirement caps, F-1 counting). Weights per strategy are listed with each option.")
ALT_BUDGET_SECONDS = 4.0
ALT_PER_COURSE = 3


def verified_alternatives(ctx: PlanContext, model: ScheduleModel, strat: Strategy, res, exclude_sets: list[set[str]]) -> dict:
    """For each scheduled course, the best other eligible courses for the same requirement(s) and a
    checked reason each lost: a rule check (not given to the solver, every section blocked, sequencing)
    or a re-solve with that course forced in (infeasible with the conflicting constraints, or feasible
    with a lower objective and the courses it would displace)."""
    pool = model.pool
    chosen = {s.course for s in res.sections}
    hard = [b for b in model.blocks if b.kind == "hard"]
    pairs = set(model.sequence_pairs)
    titles = ctx.catalog.courses
    spent, out = 0.0, {}
    for course in sorted(chosen, key=lambda c: -pool["values"].get(c, 0)):
        rids = set(pool["requirements"].get(course, [])) - {"FREE_ELECTIVE"} or set(pool["requirements"].get(course, []))
        alts = sorted({c for c, r in pool["requirements"].items() if c not in chosen and rids & set(r)}, key=lambda c: -pool["values"][c])
        rows = []
        for alt in alts[:ALT_PER_COURSE]:
            row = {"course": alt, "title": titles[alt].title if alt in titles else alt, "score": pool["values"][alt],
                   "score_of_chosen": pool["values"].get(course, 0), "verified": True}
            secs = [s for s in pool["sections"][alt] if s.component == "primary"]
            seq = [a for a, b in pairs if b == alt and a in chosen] + [b for a, b in pairs if a == alt and b in chosen]
            if alt not in pool["considered"]:
                row.update(method="candidate pool", why_not=f"Not given to the solver: {pool['pruned'].get(alt, 'lower score')} "
                           f"(its score {pool['values'][alt]:.2f} = degree priority {pool['priority'][alt]:.2f} + interest {pool['interest'][alt]:.2f}).")
            elif secs and all(overlapping_blocks(s, hard) for s in secs):
                row.update(method="rule check", why_not="Every section overlaps a time you marked unavailable.")
            elif seq:
                row.update(method="rule check", why_not=f"It can't be taken in the same term as {', '.join(seq)} (prerequisite sequence).")
            elif spent >= ALT_BUDGET_SECONDS:
                row.update(verified=False, method="not re-checked", why_not="Not re-checked: the explanation time budget for this option was used up.")
            else:
                t = time.time()
                forced = ScheduleModel(model.c, model.courses, model.blocks, model.prefs, model.caps, model.f1, model.must,
                                       student_required=[*model.student_required, alt], sequence_pairs=model.sequence_pairs)
                r = forced.solve(strat, exclude_sets=exclude_sets)
                spent += time.time() - t
                if not r.feasible:
                    why = [g.description for g in r.conflict_set if not g.key.endswith(f":{alt}")]
                    row.update(method="re-solved with it included",
                               why_not="Can't be added without breaking: " + ("; ".join(why) if why else "the other selected requirements") + ".")
                else:
                    displaced = sorted(chosen - {s.course for s in r.sections})
                    if r.objective < res.objective:
                        row.update(method="re-solved with it included", objective_with=r.objective, objective=res.objective, displaced=displaced,
                                   why_not=f"Possible, but the best {strat.label} schedule that includes it scores lower "
                                           f"({r.objective:.0f} vs {res.objective:.0f})" + (f" and would replace {', '.join(displaced)}." if displaced else "."))
                    else:
                        row.update(method="re-solved with it included", objective_with=r.objective, objective=res.objective, displaced=displaced,
                                   why_not="An equally good schedule includes it; this option was chosen first (ties are broken by the solver)"
                                           + (" or it was required to differ from an earlier option." if exclude_sets else "."))
            rows.append(row)
        out[course] = rows
    return out


CONCURRENT_RE = re.compile(r"([A-Z]{2,5} \d{4})\s*\((?:may|can) be taken concurrently\)", re.I)


def sequence_pairs(ctx: PlanContext, codes: list[str]) -> list[tuple[str, str]]:
    """A course and an unmet prerequisite of it can't be scheduled in the same term
    (e.g. SPAN 1002 and SPAN 1003), unless the bulletin allows taking them concurrently."""
    chosen = set(codes)
    pairs = []
    for code in codes:
        course = ctx.catalog.courses.get(code)
        if course is None:
            continue
        # same passing-grade rule as prerequisite checks: an F/W (or below the minimum) doesn't satisfy it
        done = {t.course for t in ctx.student.transcript if counts_as_done(t, course.min_prereq_grade)}
        concurrent = {m.upper() for m in CONCURRENT_RE.findall(course.prereq_text or "")}
        for group in course.prereqs:
            if any(c in done for c in group):
                continue
            pairs += [(pre, code) for pre in group if pre in chosen and pre != code and pre not in concurrent]
    return pairs


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
        excluded_sets += [set(x) for x in ctx.student.preferences.avoid_course_sets]
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
            option = self._option(ctx, strat, rank, res, model)
            option["alternatives"] = verified_alternatives(ctx, model, strat, res, [set(x) for x in excluded_sets])
            excluded_sets.append({s.course for s in res.sections})
            options.append(option)
            ctx.log(f"{strat.label}: {res.credits} credits, {len(res.sections)} courses, {len(res.soft_violations)} preference violation(s)",
                    courses=[s.course for s in res.sections], solver_status=res.breakdown.get("status"))

        ideal = self._ideal_analysis(ctx)
        pool = model.pool
        top_pruned = sorted(pool["pruned"], key=lambda c: -pool["values"][c])[:15]
        ctx.log(f"Candidate pool: {len(pool['considered'])} of {len(pool['values'])} eligible courses given to the solver",
                highest_scoring_not_considered={c: pool["values"][c] for c in top_pruned})
        return {"options": options, "infeasible_strategies": infeasible, "ideal_analysis": ideal,
                "solver": "Google OR-Tools CP-SAT", "strategies": [s.__dict__ for s in STRATEGIES],
                "objective": OBJECTIVE_TEXT,
                "candidate_pool": {"eligible_courses": len(pool["values"]), "considered": len(pool["considered"]),
                                   "max_courses": MAX_COURSES, "slack": PRUNE_SLACK,
                                   "not_considered": [{"course": c, "score": pool["values"][c], "reason": pool["pruned"][c]} for c in top_pruned]}}

    def _option(self, ctx: PlanContext, strat: Strategy, rank: int, res, model: ScheduleModel) -> dict:
        disc = ctx.state["course_discovery"]
        interest = ctx.state["interest_matching"]["scores"]
        grad = ctx.state["graduation_planning"]
        by_section = {e["section"]["id"]: e for e in all_eligible(ctx.state)}
        soft_count = max(1, sum(1 for b in ctx.student.availability if b.kind == "soft") + bool(ctx.student.preferences.avoid_before)
                         + bool(ctx.student.preferences.avoid_after))
        violated_prefs = {v["preference"] for v in res.soft_violations}
        critical = [c["course"] for c in grad["critical_courses"]]
        chosen = {s.course for s in res.sections}
        return {
            "id": f"{ctx.plan_id}-{strat.key}",
            "strategy": strat.key, "label": strat.label, "rank": rank, "credits": res.credits,
            "weights": {"w_req": strat.w_req, "w_int": strat.w_int, "w_soft": strat.w_soft, "w_dev": strat.w_dev,
                        "free_electives": strat.free_electives, "enforce_critical": strat.enforce_critical},
            "sections": [{**s.model_dump(), "title": ctx.catalog.courses[s.course].title if s.course in ctx.catalog.courses else s.course,
                          "credits": section_credits(s, ctx.catalog.courses),
                          "requires_linked_section": by_section[s.id].get("requires_linked_section", False),
                          "time_tba": by_section[s.id].get("time_tba", False),
                          "requirement_ids": by_section[s.id]["requirement_ids"],
                          "category": classify(s.course, by_section[s.id]["requirement_ids"], ctx.state),
                          "component_pairing": by_section[s.id].get("component_pairing", "single"),
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

    def decision(self, ctx, o):
        ideal = o["ideal_analysis"]
        return {"task": "Solve the schedule with CP-SAT for three strategies and analyze infeasibility",
                "data_sources": ["Google OR-Tools CP-SAT", "Constraints Agent output", "Eligible sections and interest electives"],
                "findings": [f"{x['label']}: {x['credits']:g} credits, {len({s['course'] for s in x['sections']})} courses, {len(x['soft_violations'])} preference conflict(s)"
                             for x in o["options"]] + [f"{i['label']}: infeasible" for i in o["infeasible_strategies"]],
                "recommendation": ("All preferences satisfiable." if ideal["perfect_exists"] else
                                   "No schedule satisfies everything; solver-verified resolutions offered."),
                "validation": {"status": "passed" if o["options"] else "failed",
                               "detail": ("Irreducible conflict set: " + "; ".join(g["description"] for g in ideal.get("conflict_set", [])))
                               if not ideal["perfect_exists"] else "Optimal or feasible solutions found"},
                "unresolved": [r["title"] for r in ideal.get("resolutions", [])][:4]}

    def summarize(self, o: dict) -> str:
        msg = f"{len(o['options'])} schedule option(s) generated with CP-SAT"
        if o["infeasible_strategies"]:
            msg += f"; {len(o['infeasible_strategies'])} strategy infeasible"
        if not o["ideal_analysis"]["perfect_exists"]:
            msg += "; no schedule satisfies every preference (conflict set computed)"
        return msg + "."
