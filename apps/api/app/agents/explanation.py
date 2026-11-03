import json

from pydantic import BaseModel

from app.agents.base import Agent, PlanContext
from app.agents.llm import structured_call, wrap_untrusted
from app.domain import SectionData
from app.rules import campus_supported, earliest_start, meets_on, overlapping_blocks, sections_conflict

DAY_LABEL = {"M": "Mon", "T": "Tue", "W": "Wed", "R": "Thu", "F": "Fri", "S": "Sat", "U": "Sun"}


class OptionSummaryOut(BaseModel):
    option_id: str
    summary: str


class NarrativeOut(BaseModel):
    overall: str
    options: list[OptionSummaryOut]


def meeting_text(sec: dict) -> str:
    if not sec["meetings"]:
        return "online, asynchronous"
    return "; ".join(f"{''.join(DAY_LABEL[d][:2] for d in m['days'])} {m['start']}-{m['end']}" for m in sec["meetings"])


class StudentExplanationAgent(Agent):
    key = "student_explanation"
    title = "Student Explanation Agent"
    responsibility = "Translates structured findings into plain-language explanations without hiding uncertainty."

    def run(self, ctx: PlanContext) -> dict:
        st = ctx.state
        reqs = {r["id"]: r for r in st["degree_requirements"]["requirements"]}
        interest = st["interest_matching"]
        disc = st["course_discovery"]
        grad = st["graduation_planning"]
        reviews = st["academic_review"]["reviews"]
        all_sections = [SectionData(**e["section"]) for e in disc["eligible_sections"]]
        hard = [b for b in ctx.student.availability if b.kind == "hard"]
        soft = [b for b in ctx.student.availability if b.kind == "soft"]

        options_out = []
        for opt in st["schedule_optimization"]["options"]:
            chosen = [SectionData(**{k: v for k, v in x.items() if k in SectionData.model_fields}) for x in opt["sections"]]
            courses = []
            for x, sec in zip(opt["sections"], chosen):
                reasons = []
                for rid in x["requirement_ids"]:
                    r = reqs[rid]
                    reasons.append({"kind": "requirement", "verified": False,
                                    "text": f"May satisfy {r['program_name']} {r['program_type']}: {r['name']} ({r['remaining_needed']} still needed)",
                                    "status": "pending_verification", "source": r["source_url"]})
                sc = interest["scores"].get(x["course"], {})
                if sc.get("score", 0) >= 0.3:
                    reasons.append({"kind": "interest", "verified": False, "ai_generated": sc.get("method") == "llm_semantic",
                                    "text": sc["reason"], "score": sc["score"]})
                pr = grad["priorities"].get(x["course"], {})
                if x["course"] in opt["critical_included"]:
                    crit = next(c for c in grad["critical_courses"] if c["course"] == x["course"])
                    reasons.append({"kind": "graduation", "verified": True, "text": f"Graduation-critical: {crit['reason']}"})
                elif pr.get("unlocks"):
                    reasons.append({"kind": "graduation", "verified": True, "text": f"Unlocks {', '.join(pr['unlocks'])}."})
                fit = []
                if not any(overlapping_blocks(sec, hard)):
                    fit.append("Outside all of your unavailable times")
                for b in soft:
                    fit.append(f"Conflicts with your preference '{b.label}'" if overlapping_blocks(sec, [b]) else f"Respects '{b.label}'")
                if not sec.meetings:
                    fit.append("Online asynchronous: no fixed meeting time")
                reasons.append({"kind": "schedule_fit", "verified": True, "text": "; ".join(fit) + "."})
                prereq = ("Prerequisites completed." if x["prereq_status"] == "satisfied" else
                          f"Conditional: requires passing in-progress {', '.join(x['prereq_pending'])}." if x["prereq_status"] == "conditional" else "")
                courses.append({
                    "section_id": sec.id, "course": sec.course, "title": x["title"], "credits": x["credits"],
                    "meeting": meeting_text(x), "modality": sec.modality, "campus": sec.campus, "location": sec.location,
                    "reasons": reasons, "prerequisites": prereq, "requirement_status": "Pending verification",
                    "section_choice": self._section_choice(sec, chosen, all_sections, hard, soft),
                    "data": {"source": sec.data_source, "retrieved_at": sec.retrieved_at, "crn": sec.crn},
                })
            tradeoffs = [v["detail"] for v in opt["soft_violations"]]
            for c in opt["critical_missing"]:
                crit = next(cc for cc in grad["critical_courses"] if cc["course"] == c)
                tradeoffs.append(f"Defers graduation-critical {c}. {crit['reason']}")
            rv = reviews.get(opt["id"], {})
            unresolved = [ch["detail"] for ch in rv.get("checks", []) if not ch["passed"]]
            options_out.append({"option_id": opt["id"], "label": opt["label"], "courses": courses, "tradeoffs": tradeoffs,
                                "unresolved": unresolved, "review_status": rv.get("status"),
                                "summary": self._template_summary(opt, tradeoffs)})

        alternatives = []
        in_any = {x["course"] for o in st["schedule_optimization"]["options"] for x in o["sections"]}
        eligible_ranked = [c for c in interest["ranking"] if c in {e["course"] for e in disc["eligible_sections"]}]
        for b in interest["blocked_high_interest"]:
            alts = [c for c in eligible_ranked if c != b["course"]][:2]
            alternatives.append({"course": b["course"], "title": b["title"],
                                 "message": f"{b['course']} {b['title']} matches your interests, but you have not completed its prerequisite ({b['missing_prereq']}).",
                                 "eligible_alternatives": [{"course": c, "title": disc["courses"][c]["title"], "in_a_schedule": c in in_any} for c in alts]})

        ideal = st["schedule_optimization"]["ideal_analysis"]
        headline = ("We found a schedule that satisfies all of your preferences." if ideal["perfect_exists"] else
                    "We couldn't find a schedule that satisfies all your preferences.")
        why = [g["description"] for g in ideal.get("conflict_set", [])]
        pre = [p["detail"] for p in st["scheduling_constraints"]["pre_checks"]]

        narrative = self._narrative(ctx, options_out, headline, why + pre)
        if narrative:
            for o in options_out:
                o["ai_summary"] = narrative["options"].get(o["option_id"])
        return {"headline": headline, "conflict_explanation": {"constraints_in_conflict": why, "details": pre,
                                                               "minimal": ideal.get("minimal", False),
                                                               "resolutions": ideal.get("resolutions", [])},
                "options": options_out, "blocked_interest_alternatives": alternatives,
                "overall_ai_summary": narrative["overall"] if narrative else None,
                "disclaimer": "Planning assistance only. Not an official degree audit, registration, or immigration advice. Confirm with your academic advisor and ISSS."}

    def _section_choice(self, sec, chosen, all_sections, hard, soft) -> str:
        others = [s for s in all_sections if s.course == sec.course and s.id != sec.id]
        if not others:
            return f"Section {sec.section} is the only eligible section this term."
        why = []
        for o in others:
            if overlapping_blocks(o, hard):
                why.append(f"{o.section} overlaps {overlapping_blocks(o, hard)[0].label}")
            elif any(sections_conflict(o, c) for c in chosen if c.course != sec.course):
                clash = next(c for c in chosen if c.course != sec.course and sections_conflict(o, c))
                why.append(f"{o.section} conflicts with {clash.course}")
            elif not campus_supported(o):
                why.append(f"{o.section} is at {o.campus}")
            elif overlapping_blocks(o, soft):
                why.append(f"{o.section} conflicts with '{overlapping_blocks(o, soft)[0].label}'")
            else:
                why.append(f"{o.section} scored lower on your preferences")
        return f"Chose section {sec.section}; " + "; ".join(why) + "."

    def _template_summary(self, opt: dict, tradeoffs: list[str]) -> str:
        n = len(opt["sections"])
        friday = not any(meets_on(SectionData(**{k: v for k, v in x.items() if k in SectionData.model_fields}), "F") for x in opt["sections"])
        early = min((earliest_start(SectionData(**{k: v for k, v in x.items() if k in SectionData.model_fields})) or 1440) for x in opt["sections"])
        parts = [f"{n} courses, {opt['credits']} credits."]
        parts.append("No Friday classes." if friday else "Includes Friday class time.")
        if early < 1440:
            parts.append(f"Earliest class starts at {early // 60}:{early % 60:02d}.")
        if tradeoffs:
            parts.append(f"{len(tradeoffs)} tradeoff(s) to review.")
        return " ".join(parts)

    def _narrative(self, ctx: PlanContext, options: list[dict], headline: str, conflicts: list[str]) -> dict | None:
        facts = [{"option_id": o["option_id"], "label": o["label"],
                  "courses": [f"{c['course']} {c['title']} ({c['meeting']})" for c in o["courses"]],
                  "tradeoffs": o["tradeoffs"], "unresolved": o["unresolved"][:4]} for o in options]
        out = structured_call(
            system=("You are the Student Explanation Agent. Write a friendly 2-3 sentence summary for each schedule option and a "
                    "2-sentence overall note, using ONLY the facts provided. Never claim anything is verified, official or "
                    "immigration-compliant. Always mention tradeoffs and unresolved issues when present."),
            user=f"Headline: {headline}\nConflicts: {conflicts}\n" + wrap_untrusted("planner_facts", json.dumps(facts)),
            schema=NarrativeOut,
        )
        if out is None:
            ctx.set_mode("llm_fallback" if ctx.state.get("_llm_enabled") else "deterministic")
            return None
        ctx.set_mode("llm")
        ids = {o["option_id"] for o in options}
        return {"overall": out.overall, "options": {s.option_id: s.summary for s in out.options if s.option_id in ids}}

    def summarize(self, o: dict) -> str:
        return f"{o['headline']} Explained {sum(len(x['courses']) for x in o['options'])} course recommendations."
