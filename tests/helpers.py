from app.domain import AvailBlock, CourseData, Meeting, PlanningPreferences, RequirementData, SectionData


def course(code, credits=3, prereqs=None):
    return CourseData(code=code, title=code, credits=credits, description="", prereqs=prereqs or [])


def section(sid, course_code, meetings, modality="in_person", campus="Main"):
    return SectionData(id=sid, course=course_code, term_id="2027-SP", section=sid[-3:], crn=sid, instructor="Staff",
                       campus=campus, modality=modality, location="X",
                       meetings=[Meeting(days=d, start=s, end=e) for d, s, e in meetings],
                       seats_available=10, data_source="demo_fixture", retrieved_at="2026-10-15T00:00:00")


def req(rid, courses, rule="all", n=None, program="P", ptype="major"):
    return RequirementData(id=rid, program_id=program, program_name=program, program_type=ptype, name=rid, rule=rule,
                           choose_count=n, courses=courses, category="core", catalog_year="2024-2025",
                           verification_status="demo_unverified")


def block(day, start, end, kind="hard", label="Work"):
    return AvailBlock(day=day, start=start, end=end, kind=kind, label=label)


def prefs(**kw):
    base = dict(credit_target=9, credit_min=3, credit_max=12)
    base.update(kw)
    return PlanningPreferences(**base)
