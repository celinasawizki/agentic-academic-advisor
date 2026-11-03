from app.agents.base import Agent, PlanContext
from app.rules import campus_supported, prereq_status


class CourseDiscoveryAgent(Agent):
    key = "course_discovery"
    title = "Course Discovery Agent"
    responsibility = "Searches the course-section adapter for the planning term and filters by campus, prerequisites and seats."

    def run(self, ctx: PlanContext) -> dict:
        req_out = ctx.state["degree_requirements"]
        wanted: dict[str, list[str]] = {}
        for r in req_out["remaining"]:
            for c in r["candidate_courses"]:
                wanted.setdefault(c, []).append(r["id"])
        excluded_courses = set(ctx.student.preferences.excluded_courses)
        ctx.log(f"Searching {ctx.catalog.term_name} sections for {len(wanted)} requirement-eligible courses")
        ctx.cite("course_search", f"{ctx.catalog.term_name} section fixture (DemoFixtureCourseSearchAdapter)",
                 None, None, "demo_unverified")

        eligible, excluded, course_info = [], [], {}
        for code, req_ids in wanted.items():
            course = ctx.catalog.courses.get(code)
            if course is None:
                excluded.append({"course": code, "reason": "Not found in course dataset"})
                continue
            pre = prereq_status(course, ctx.student.transcript)
            course_info[code] = {"code": code, "title": course.title, "credits": course.credits,
                                 "description": course.description, "requirement_ids": req_ids,
                                 "prereq_status": pre.status, "prereq_missing": pre.missing_groups,
                                 "prereq_pending": pre.pending_courses}
            secs = [s for s in ctx.catalog.sections if s.course == code and s.term_id == ctx.catalog.term_id]
            if not secs:
                excluded.append({"course": code, "reason": f"No sections offered in {ctx.catalog.term_name} in the dataset"})
                continue
            if code in excluded_courses:
                excluded.append({"course": code, "reason": "Excluded at the student's request"})
                continue
            if pre.status == "missing":
                need = " and ".join(" or ".join(g) for g in pre.missing_groups)
                excluded.append({"course": code, "reason": f"Prerequisite not completed: {need}", "kind": "prerequisite"})
                continue
            for sec in secs:
                if not campus_supported(sec):
                    excluded.append({"course": code, "section": sec.id, "reason": f"{sec.campus} campus is not supported in this prototype"})
                    continue
                if sec.seats_available is not None and sec.seats_available <= 0:
                    excluded.append({"course": code, "section": sec.id, "reason": "No seats available"})
                    continue
                eligible.append({"section": sec.model_dump(), "course": code, "requirement_ids": req_ids,
                                 "prereq_status": pre.status, "prereq_pending": pre.pending_courses})
        ctx.log(f"{len(eligible)} eligible sections across {len({e['course'] for e in eligible})} courses; {len(excluded)} exclusions",
                exclusions=[f"{e['course']}: {e['reason']}" for e in excluded])
        return {"term_id": ctx.catalog.term_id, "term_name": ctx.catalog.term_name, "eligible_sections": eligible,
                "excluded": excluded, "courses": course_info, "data_source": "demo_fixture"}

    def summarize(self, o: dict) -> str:
        return (f"{len(o['eligible_sections'])} eligible sections for {len({e['course'] for e in o['eligible_sections']})} courses "
                f"in {o['term_name']}; {len(o['excluded'])} sections/courses excluded with reasons.")
