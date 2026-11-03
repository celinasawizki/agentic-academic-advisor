from collections import Counter

from app.agents.base import Agent, PlanContext
from app.domain import RequirementData, SectionData
from app.rules import campus_supported, prereq_status

ARRANGED_TYPES = ("independent study", "dissertation", "research", "thesis", "private instruction", "internship",
                  "practicum", "field", "clinical", "student teaching", "directed")


def course_record(c, pre, req_ids: list[str], offered: bool) -> dict:
    return {"code": c.code, "title": c.title, "credits": c.credits, "description": c.description[:600],
            "requirement_ids": req_ids, "prereq_status": pre.status, "prereq_missing": pre.missing_groups,
            "prereq_pending": pre.pending_courses, "prereq_unverifiable": pre.unverifiable, "prereq_notes": pre.notes,
            "prereq_text": c.prereq_text, "attributes": c.attributes, "offered": offered}


def evaluate_course(c, secs: list[SectionData], student, excluded_courses: set[str], term_name: str) -> dict:
    """Deterministic eligibility of one course for the planning term. Returns usable section
    entries, or the reason the course cannot be scheduled. Shared by Course Discovery and
    the Interest Matching Agent's elective search."""
    pre = prereq_status(c, student.transcript)
    out = {"prereq": pre, "eligible": [], "reason": None, "notes": [], "blocked": False}
    if not secs:
        out["reason"] = f"Not offered in {term_name} (no sections in the class-search snapshot)"
        return out
    if c.code in excluded_courses:
        out["reason"] = "Excluded at the student's request"
        return out
    if pre.status == "missing":
        need = " and ".join("(" + " or ".join(g) + ")" for g in pre.missing_groups)
        out["reason"], out["blocked"] = f"Prerequisite not completed: {need}" + (f" — {'; '.join(pre.notes)}" if pre.notes else ""), True
        return out
    arranged = [x for x in secs if not x.meetings and any(t in (x.schedule_type or "").lower() for t in ARRANGED_TYPES)]
    secs = [x for x in secs if x not in arranged]
    if not secs:
        out["reason"] = "Arranged individually (independent study/research/internship) — needs instructor or department approval"
        return out
    campus_bad = [s for s in secs if not campus_supported(s)]
    full = [s for s in secs if campus_supported(s) and s.seats_available is not None and s.seats_available <= 0]
    usable = [s for s in secs if campus_supported(s) and s not in full]
    comps = {x.component for x in secs}
    usable_comps = {x.component for x in usable}
    if campus_bad:
        out["notes"].append({"reason": f"{len(campus_bad)} section(s) at unsupported campuses ({', '.join(sorted({s.campus for s in campus_bad}))})"})
    if full:
        out["notes"].append({"reason": f"{len(full)} section(s) full in the snapshot (seat counts are as of the snapshot date, not live)"})
    if not usable:
        out["reason"] = "No open Main Campus or online section"
        return out
    if usable_comps != comps:
        out["reason"] = f"No open Main Campus/online section for component(s): {', '.join(sorted(comps - usable_comps))}"
        return out
    for sec in usable:
        out["eligible"].append({"section": sec.model_dump(), "course": c.code, "prereq_status": pre.status,
                                "prereq_pending": pre.pending_courses, "component": sec.component,
                                "components": sorted(usable_comps), "component_pairing": "inferred" if len(usable_comps) > 1 else "single",
                                "requires_linked_section": sec.linked, "time_tba": not sec.meetings and sec.modality != "online"})
    return out


class CourseDiscoveryAgent(Agent):
    key = "course_discovery"
    title = "Course Discovery Agent"
    responsibility = "Searches the term's sections for every requirement (explicit lists, course ranges and GenEd attributes); filters campus, prerequisites and seats."

    def run(self, ctx: PlanContext) -> dict:
        remaining = ctx.state["degree_requirements"]["remaining"]
        reqs = {r.id: r for r in ctx.catalog.requirements}
        courses = ctx.catalog.courses
        done = {t.course for t in ctx.student.transcript if t.status in ("completed", "transfer", "in_progress")}
        term_secs = [s for s in ctx.catalog.sections if s.term_id == ctx.catalog.term_id]
        by_course: dict[str, list[SectionData]] = {}
        for s in term_secs:
            by_course.setdefault(s.course, []).append(s)

        wanted: dict[str, list[str]] = {}
        explicit: set[str] = set()
        for r in remaining:
            for c in r["candidate_courses"]:
                wanted.setdefault(c, []).append(r["id"])
                explicit.add(c)
        pattern_reqs: list[RequirementData] = [reqs[r["id"]] for r in remaining if reqs.get(r["id"]) and reqs[r["id"]].patterns]
        for code, secs in by_course.items():
            c = courses.get(code)
            if not c or code in done:
                continue
            attrs = sorted({a for s in secs for a in s.attributes})
            for pr in pattern_reqs:
                if pr.pattern_matches(c, attrs) and pr.id not in wanted.get(code, []):
                    wanted.setdefault(code, []).append(pr.id)

        excluded_courses = set(ctx.student.preferences.excluded_courses)
        ctx.log(f"Searching {len(term_secs)} {ctx.catalog.term_name} sections for {len(explicit)} listed courses and "
                f"{len(pattern_reqs)} range/attribute rules → {len(wanted)} requirement-relevant courses")
        ctx.cite("course_search", f"{ctx.catalog.term_name} snapshot of Temple's public class search ({len(term_secs)} sections)",
                 "https://prd-xereg.temple.edu/StudentRegistrationSsb/ssb/classSearch/classSearch",
                 term_secs[0].retrieved_at if term_secs else None, "snapshot")

        eligible, excluded, course_info = [], [], {}
        pattern_skips: Counter = Counter()
        for code, req_ids in wanted.items():
            c = courses.get(code)
            is_explicit = code in explicit
            if c is None:
                (excluded.append({"course": code, "reason": "Not found in the bulletin course catalog"}) if is_explicit
                 else pattern_skips.update(["Not found in the bulletin course catalog"]))
                continue
            ev = evaluate_course(c, by_course.get(code, []), ctx.student, excluded_courses, ctx.catalog.term_name)
            course_info[code] = course_record(c, ev["prereq"], req_ids, code in by_course)
            if is_explicit:
                excluded.extend({"course": code, **n} for n in ev["notes"])
            if ev["reason"]:
                if is_explicit:
                    excluded.append({"course": code, "reason": ev["reason"], **({"kind": "prerequisite"} if ev["blocked"] else {})})
                else:
                    pattern_skips.update([ev["reason"].split(":")[0]])
                continue
            for entry in ev["eligible"]:
                eligible.append({**entry, "requirement_ids": req_ids, "explicit": is_explicit})

        availability = {}
        eligible_reqs = {rid for e in eligible for rid in e["requirement_ids"]}
        for r in remaining:
            if r["id"] in eligible_reqs:
                availability[r["id"]] = {"status": "available", "reason": "Eligible sections exist this term."}
            elif any(course_info.get(c, {}).get("prereq_status") == "missing" and course_info[c]["offered"] for c in r["candidate_courses"]):
                availability[r["id"]] = {"status": "blocked", "reason": f"Offered courses for this rule are blocked by prerequisites in {ctx.catalog.term_name}."}
            else:
                availability[r["id"]] = {"status": "unavailable", "reason": f"No eligible Main Campus/online section in {ctx.catalog.term_name}."}
        # Shared-state update with evidence: open rules that cannot progress this term.
        changed = []
        for p in ctx.state["degree_requirements"]["requirements"]:
            a = availability.get(p["id"])
            if a and a["status"] in ("blocked", "unavailable") and p.get("reliability") in ("PENDING_VERIFICATION", "VERIFIED"):
                p["reliability"], p["reliability_reason"] = a["status"].upper(), a["reason"]
                changed.append(p["id"])
        if changed:
            ctx.log(f"{len(changed)} open requirement rule(s) cannot progress this term (marked BLOCKED/UNAVAILABLE)", rules=changed[:20])
        ctx.log(f"{len(eligible)} eligible sections across {len({e['course'] for e in eligible})} courses; "
                f"{len(excluded)} listed-course exclusions", exclusions=[f"{e['course']}: {e['reason']}" for e in excluded[:40]])
        if pattern_skips:
            ctx.log("Range/attribute matches skipped (summary)", **dict(pattern_skips.most_common(6)))
        return {"term_id": ctx.catalog.term_id, "term_name": ctx.catalog.term_name, "eligible_sections": eligible,
                "excluded": excluded, "pattern_exclusion_summary": dict(pattern_skips), "courses": course_info,
                "requirement_availability": availability,
                "data_source": "temple_class_search_snapshot"}

    def summarize(self, o: dict) -> str:
        return (f"{len(o['eligible_sections'])} eligible sections for {len({e['course'] for e in o['eligible_sections']})} courses "
                f"in {o['term_name']}; {len(o['excluded'])} listed-course exclusions with reasons.")
