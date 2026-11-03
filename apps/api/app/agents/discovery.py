from collections import Counter

from app.agents.base import Agent, PlanContext
from app.domain import RequirementData, SectionData
from app.rules import campus_supported, prereq_status

SECONDARY_TYPES = ("recitation", "laboratory", "lab", "discussion")
ARRANGED_TYPES = ("independent study", "dissertation", "research", "thesis", "private instruction", "internship",
                  "practicum", "field", "clinical", "student teaching", "directed")


def component_of(sec: SectionData, all_types: set[str]) -> str:
    """'primary' for the main meeting (lecture / lecture+lab ...); otherwise the separate
    component type (Lab, Recitation, ...) that must also be scheduled."""
    t = (sec.schedule_type or "").strip()
    if t.lower() in SECONDARY_TYPES and any(x.lower() not in SECONDARY_TYPES for x in all_types):
        return t
    return "primary"


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
            note = (lambda reason, **kw: excluded.append({"course": code, "reason": reason, **kw})) if is_explicit else (lambda reason, **kw: pattern_skips.update([reason.split(":")[0]]))
            if c is None:
                note("Not found in the bulletin course catalog")
                continue
            pre = prereq_status(c, ctx.student.transcript)
            course_info[code] = {"code": code, "title": c.title, "credits": c.credits, "description": c.description[:600],
                                 "requirement_ids": req_ids, "prereq_status": pre.status, "prereq_missing": pre.missing_groups,
                                 "prereq_pending": pre.pending_courses, "prereq_unverifiable": pre.unverifiable,
                                 "prereq_text": c.prereq_text, "attributes": c.attributes, "offered": code in by_course}
            secs = by_course.get(code, [])
            if not secs:
                note(f"Not offered in {ctx.catalog.term_name} (no sections in the class-search snapshot)")
                continue
            if code in excluded_courses:
                note("Excluded at the student's request")
                continue
            if pre.status == "missing":
                need = " and ".join("(" + " or ".join(g) + ")" for g in pre.missing_groups)
                note(f"Prerequisite not completed: {need}", kind="prerequisite")
                continue
            arranged = [x for x in secs if not x.meetings and any(t in (x.schedule_type or "").lower() for t in ARRANGED_TYPES)]
            secs = [x for x in secs if x not in arranged]
            if not secs:
                note("Arranged individually (independent study/research/internship) — needs instructor or department approval")
                continue
            types = {x.schedule_type or "" for x in secs}
            campus_bad = [s for s in secs if not campus_supported(s)]
            full = [s for s in secs if campus_supported(s) and s.seats_available is not None and s.seats_available <= 0]
            usable = [s for s in secs if campus_supported(s) and s not in full]
            comps = {component_of(x, types) for x in secs}
            usable_comps = {component_of(x, types) for x in usable}
            if usable and usable_comps != comps:
                note(f"No open Main Campus/online section for required component(s): {', '.join(sorted(comps - usable_comps))}")
                continue
            if campus_bad and is_explicit:
                excluded.append({"course": code, "reason": f"{len(campus_bad)} section(s) at unsupported campuses ({', '.join(sorted({s.campus for s in campus_bad}))})"})
            if full and is_explicit:
                excluded.append({"course": code, "reason": f"{len(full)} full section(s) (waitlist only in snapshot)"})
            if not usable:
                note("No open Main Campus or online section")
                continue
            for sec in usable:
                tba = not sec.meetings and sec.modality != "online"
                eligible.append({"section": sec.model_copy(update={"component": component_of(sec, types)}).model_dump(), "course": code, "requirement_ids": req_ids,
                                 "prereq_status": pre.status, "prereq_pending": pre.pending_courses,
                                 "component": component_of(sec, types), "components": sorted(usable_comps),
                                 "requires_linked_section": sec.linked, "time_tba": tba, "explicit": is_explicit})
        ctx.log(f"{len(eligible)} eligible sections across {len({e['course'] for e in eligible})} courses; "
                f"{len(excluded)} listed-course exclusions", exclusions=[f"{e['course']}: {e['reason']}" for e in excluded[:40]])
        if pattern_skips:
            ctx.log("Range/attribute matches skipped (summary)", **dict(pattern_skips.most_common(6)))
        return {"term_id": ctx.catalog.term_id, "term_name": ctx.catalog.term_name, "eligible_sections": eligible,
                "excluded": excluded, "pattern_exclusion_summary": dict(pattern_skips), "courses": course_info,
                "data_source": "temple_class_search_snapshot"}

    def summarize(self, o: dict) -> str:
        return (f"{len(o['eligible_sections'])} eligible sections for {len({e['course'] for e in o['eligible_sections']})} courses "
                f"in {o['term_name']}; {len(o['excluded'])} listed-course exclusions with reasons.")
