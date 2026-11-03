import json

from pydantic import BaseModel

from app.agents.base import Agent, PlanContext
from app.agents.categories import DEGREE_ELECTIVE, INTEREST_ELECTIVE, LABELS, all_eligible, classify
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
        eligible = all_eligible(st)
        all_sections = [SectionData(**e["section"]) for e in eligible]
        hard = [b for b in ctx.student.availability if b.kind == "hard"]
        soft = [b for b in ctx.student.availability if b.kind == "soft"]
        req_courses: dict[str, set[str]] = {}
        for e in disc["eligible_sections"]:
            for rid in e["requirement_ids"]:
                req_courses.setdefault(rid, set()).add(e["course"])

        options_out = []
        for opt in st["schedule_optimization"]["options"]:
            chosen = [SectionData(**{k: v for k, v in x.items() if k in SectionData.model_fields}) for x in opt["sections"]]
            in_option = {c.course for c in chosen}
            courses = []
            for x, sec in zip(opt["sections"], chosen):
                provenance = self._provenance(ctx, sec, x)
                if sec.component != "primary":
                    fit = "Outside all of your unavailable times." if not overlapping_blocks(sec, hard) else ""
                    courses.append({
                        "section_id": sec.id, "course": sec.course, "title": f"{x['title']} — {sec.component}", "credits": 0,
                        "category": x.get("category", DEGREE_ELECTIVE), "category_label": f"{sec.component} component",
                        "meeting": meeting_text(x), "modality": sec.modality, "campus": sec.campus, "location": sec.location,
                        "reasons": [{"kind": "schedule_fit", "verified": True,
                                     "text": f"{sec.component} section scheduled with {sec.course} because the course is also offered with separate {sec.component.lower()} sections. {fit}".strip()}],
                        "prerequisites": "", "requirement_status": "Component of a recommended course",
                        "section_choice": self._section_choice(sec, chosen, [a for a in all_sections if a.component == sec.component], hard, soft),
                        "alternatives_considered": [],
                        "unverified": ["Lecture/lab pairing is inferred from schedule types; Temple's class search publishes no section linkage. TUportal may require a specific pairing."],
                        "data": provenance,
                    })
                    continue
                category = x.get("category") or classify(sec.course, x["requirement_ids"], st)
                reasons, unverified = [], []
                if category == INTEREST_ELECTIVE:
                    reasons.append({"kind": "requirement", "verified": True,
                                    "text": "Does not satisfy any parsed requirement in your programs. It would count only toward general/free elective credit, if your degree allows it.",
                                    "status": "not_a_requirement"})
                    unverified.append("Whether free-elective credit is available in your degree plan (check your degree audit).")
                for rid in [r for r in x["requirement_ids"] if r in reqs]:
                    r = reqs[rid]
                    still = f"{r['remaining_needed']:g} credits still needed" if r["kind"] == "credits" else f"{r['remaining_needed']:g} still needed"
                    label = r["name"] if not r["group"] or r["group"] in r["name"] else f"{r['group']} — {r['name']}"
                    status = r.get("reliability", "PENDING_VERIFICATION")
                    reasons.append({"kind": "requirement", "verified": status == "VERIFIED",
                                    "text": f"May satisfy {r['program_name']}: {label} ({still})",
                                    "status": status, "source": r["source_url"]})
                    if status != "VERIFIED":
                        unverified.append(f"{r['program_name']} rule '{label}' was parsed automatically from the bulletin ({status.replace('_', ' ').lower()}).")
                sc = interest["scores"].get(x["course"], {})
                if sc.get("score", 0) >= 0.3:
                    reasons.append({"kind": "interest", "verified": False, "ai_generated": sc.get("method") == "llm_semantic",
                                    "text": sc["reason"], "score": sc["score"]})
                pr = grad["priorities"].get(x["course"], {})
                if x["course"] in opt["critical_included"]:
                    crit = next(c for c in grad["critical_courses"] if c["course"] == x["course"])
                    reasons.append({"kind": "graduation", "verified": True, "text": f"Graduation-critical: {crit['reason']}"})
                elif pr.get("unlocks"):
                    reasons.append({"kind": "graduation", "verified": True, "text": f"Prerequisite for {', '.join(pr['unlocks'][:5])}."})
                fit = []
                if not any(overlapping_blocks(sec, hard)):
                    fit.append("Outside all of your unavailable times")
                for b in soft:
                    fit.append(f"Conflicts with your preference '{b.label}'" if overlapping_blocks(sec, [b]) else f"Respects '{b.label}'")
                if not sec.meetings:
                    fit.append("Online asynchronous: no fixed meeting time" if sec.modality == "online" else "No published meeting time (TBA)")
                reasons.append({"kind": "schedule_fit", "verified": True, "text": "; ".join(fit) + "."})
                info = disc["courses"].get(x["course"]) or {}
                prereq_text = ctx.catalog.courses[x["course"]].prereq_text if x["course"] in ctx.catalog.courses else ""
                if x["prereq_status"] == "satisfied":
                    prereq = "Prerequisites completed." if prereq_text else "No prerequisites listed in the bulletin."
                else:
                    prereq = f"Conditional: requires passing in-progress {', '.join(x['prereq_pending'])}." if x["prereq_pending"] else "Conditional."
                    if info.get("prereq_unverifiable"):
                        prereq += " Part of the prerequisite can be met by placement or test scores, which the planner cannot verify."
                        unverified.append("Placement/test-score prerequisites.")
                    if x["prereq_pending"]:
                        unverified.append(f"Passing in-progress {', '.join(x['prereq_pending'])}.")
                cat_notes = ctx.catalog.courses[x["course"]].prereq_notes if x["course"] in ctx.catalog.courses else []
                for n in cat_notes:
                    if "non-course condition" in n or n.startswith("Non-course prerequisite"):
                        prereq += " Some conditions (e.g. class standing or 'any course at a level') are not checked automatically."
                        unverified.append("Prerequisite conditions that are not specific courses (see bulletin text).")
                        break
                if sec.credits_max and sec.credits and sec.credits_max > sec.credits:
                    unverified.append(f"Variable credit ({sec.credits:g}–{sec.credits_max:g}); the planner counted {sec.credits:g}.")
                if x.get("component_pairing") == "inferred":
                    unverified.append("Lecture/lab/recitation pairing (inferred, not published by Temple).")
                unverified.append(provenance["availability_status"])
                courses.append({
                    "section_id": sec.id, "course": sec.course, "title": x["title"], "credits": x["credits"],
                    "category": category, "category_label": LABELS[category],
                    "meeting": meeting_text(x), "modality": sec.modality, "campus": sec.campus, "location": sec.location,
                    "reasons": reasons, "prerequisites": prereq, "prerequisite_text": prereq_text,
                    "requirement_status": "Not a degree requirement" if category == INTEREST_ELECTIVE else "Pending verification",
                    "section_choice": self._section_choice(sec, chosen, all_sections, hard, soft),
                    "alternatives_considered": self._alternatives(ctx, x, chosen, in_option, req_courses, all_sections, hard),
                    "unverified": unverified, "data": provenance,
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
        headline = ("We found a schedule that satisfies all of your preferences." if ideal["perfect_exists"]
                    else self._conflict_headline(ctx, ideal.get("conflict_set", [])))
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
                "enrichment": interest.get("enrichment", []),
                "overall_ai_summary": narrative["overall"] if narrative else None,
                "disclaimer": "Planning assistance only. Not an official degree audit, registration, or immigration advice. Confirm with your academic advisor and ISSS."}

    def _conflict_headline(self, ctx: PlanContext, conflict_set: list[dict]) -> str:
        """Plain-language sentence built only from the solver's conflict set."""
        prefs, hard, courses, other = [], [], [], []
        for g in conflict_set:
            d = g["description"]
            if g["kind"] == "availability" and d.startswith("Preference: "):
                prefs.append(f"'{d.removeprefix('Preference: ')}'")
            elif g["kind"] == "availability":
                hard.append(d.removeprefix("Unavailable: "))
            elif g["kind"] in ("must_course", "student_required"):
                courses.append(g["key"].split(":", 1)[1])
            elif g["kind"] == "credit_min":
                other.append(f"at least {ctx.student.preferences.credit_min} credits")
            elif g["kind"] == "f1_full_time":
                other.append("the F-1 full-time count")
        hard_text = " and ".join(hard) if len(hard) <= 2 else ", ".join(hard[:-1]) + " and " + hard[-1]
        keep = prefs + ([f"your {hard_text} hours"] if hard else []) + other
        target = f"{ctx.student.preferences.credit_target}-credit schedule"
        if courses and keep:
            return (f"We couldn't find a {target} that keeps {' and '.join(keep)} while including {', '.join(courses)}: "
                    f"every eligible section of {', '.join(courses)} conflicts with them.")
        if keep:
            return f"We couldn't find a {target} that satisfies {' and '.join(keep)} at the same time."
        return "We couldn't find a schedule that satisfies all your preferences."

    def _provenance(self, ctx: PlanContext, sec: SectionData, x: dict) -> dict:
        date = (sec.retrieved_at or "")[:10]
        seats = (f"{sec.seats_available} seat(s) open as of {date} (snapshot, not live)" if sec.seats_available is not None
                 else f"Seat count not available in the snapshot ({date})")
        return {"term": ctx.catalog.term_name, "term_id": sec.term_id, "course": sec.course, "crn": sec.crn,
                "section": sec.section, "campus": sec.campus, "modality": sec.modality, "meetings": meeting_text(x),
                "instructor": sec.instructor, "source": sec.data_source, "retrieved_at": sec.retrieved_at,
                "seats": seats,
                "availability_status": f"Seats and times are from a {date} class-search snapshot and are not live; verify in TUportal."
                if sec.data_source != "demo_fixture" else "Synthetic test fixture data, not Temple data."}

    def _alternatives(self, ctx: PlanContext, x: dict, chosen: list[SectionData], in_option: set[str],
                      req_courses: dict[str, set[str]], all_sections: list[SectionData], hard) -> list[dict]:
        """Other eligible courses for the same requirement(s), and why each was not chosen."""
        st = ctx.state
        scores = st["interest_matching"]["scores"]
        pri = st["graduation_planning"]["priorities"]
        mine = pri.get(x["course"], {}).get("priority", 0.1) + scores.get(x["course"], {}).get("score", 0)
        cands = sorted({c for rid in x["requirement_ids"] for c in req_courses.get(rid, set())} - in_option,
                       key=lambda c: -(pri.get(c, {}).get("priority", 0.3) + scores.get(c, {}).get("score", 0)))[:3]
        out = []
        for c in cands:
            secs = [s for s in all_sections if s.course == c and s.component == "primary"]
            free = [s for s in secs if not overlapping_blocks(s, hard)]
            clash = [s for s in free if any(sections_conflict(s, o) for o in chosen if o.course != x["course"])]
            value = pri.get(c, {}).get("priority", 0.3) + scores.get(c, {}).get("score", 0)
            if not free:
                why = "every section overlaps your unavailable times"
            elif len(clash) == len(free):
                why = "its sections clash with other courses in this option"
            elif value < mine:
                why = f"lower combined degree-priority and interest score ({value:.2f} vs {mine:.2f})"
            else:
                why = "the optimizer preferred a different combination for overall credits and preferences"
            title = ctx.catalog.courses[c].title if c in ctx.catalog.courses else c
            out.append({"course": c, "title": title, "why_not": why})
        return out

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

    def decision(self, ctx, o):
        n_unver = sum(len(c.get("unverified", [])) for x in o["options"] for c in x["courses"])
        return {"task": "Explain every recommendation in plain language without hiding uncertainty",
                "data_sources": ["All agent outputs in the shared plan state"],
                "findings": [o["headline"], f"{sum(len(x['courses']) for x in o['options'])} course explanation(s), {n_unver} unverified item(s) disclosed"],
                "recommendation": "Show requirement, interest, prerequisite, section choice, alternatives and provenance for each course.",
                "validation": {"status": "passed", "detail": "Every claim traces to a structured agent output"},
                "unresolved": [o["disclaimer"]]}

    def summarize(self, o: dict) -> str:
        return f"{o['headline']} Explained {sum(len(x['courses']) for x in o['options'])} course recommendations."
