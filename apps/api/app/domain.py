"""Typed planning-domain objects shared by agents, rules engine and optimizer.
These are serializable into the PlanRun shared state."""

from typing import Literal

from pydantic import BaseModel, Field

Day = Literal["M", "T", "W", "R", "F", "S", "U"]
DAYS: list[str] = ["M", "T", "W", "R", "F", "S", "U"]


class Meeting(BaseModel):
    days: str
    start: str
    end: str


class SectionData(BaseModel):
    id: str
    course: str
    term_id: str
    section: str
    crn: str
    instructor: str
    campus: str
    modality: Literal["in_person", "online", "hybrid", "unknown"]
    location: str
    meetings: list[Meeting] = []
    seats_available: int | None = None
    credits: float | None = None
    credits_max: float | None = None
    schedule_type: str | None = None
    component: str = "primary"  # or the separate component type that must also be taken (Lab, Recitation)
    linked: bool = False
    attributes: list[str] = []
    data_source: str
    retrieved_at: str


class CourseData(BaseModel):
    code: str
    title: str
    credits: float
    description: str
    prereqs: list[list[str]] = []
    prereq_text: str = ""
    prereq_notes: list[str] = []
    attributes: list[str] = []

    @property
    def subject(self) -> str:
        return self.code.split()[0]

    @property
    def min_prereq_grade(self) -> str | None:
        import re
        m = re.search(r"(?i)minimum grade of ([A-D][+-]?)(?![A-Za-z0-9+-])", self.prereq_text or "")
        return m.group(1).upper() if m else None

    @property
    def number(self) -> int:
        return int(self.code.split()[1])


class RequirementData(BaseModel):
    id: str
    program_id: str
    program_name: str
    program_type: str
    group: str = ""
    name: str
    kind: Literal["count", "credits", "milestone", "policy", "manual", "note"]
    needed: float
    options: list[list[str]] = []
    patterns: list[dict] = []
    notes: list[str] = []
    catalog_year: str | None = None
    verification_status: str
    source_url: str | None = None
    min_grade: str | None = None  # minimum grade for a course to count (program or school rule)
    evidence: str | None = None  # verbatim bulletin quote (school/university layers)

    @property
    def courses(self) -> list[str]:
        return [c for opt in self.options for c in opt]

    def pattern_matches(self, course: "CourseData", section_attrs: list[str] | None = None) -> bool:
        for p in self.patterns:
            if "metric" in p:
                continue
            if "attribute" in p:
                if p["attribute"] in course.attributes or p["attribute"] in (section_attrs or []):
                    return True
            elif p.get("subject") == course.subject and p.get("min", 0) <= course.number <= p.get("max", 9999):
                return True
        return False


class TranscriptItem(BaseModel):
    course: str
    status: Literal["completed", "in_progress", "transfer", "planned", "unverified"]
    grade: str | None = None
    term: str | None = None
    source: str = "manual"
    confidence: float = 1.0


class AvailBlock(BaseModel):
    day: Day
    start: str
    end: str
    kind: Literal["hard", "soft", "preferred"]
    label: str = ""


class PlanningPreferences(BaseModel):
    credit_target: int = 15
    credit_min: int = 12
    credit_max: int = 18
    avoid_before: str | None = None  # soft: e.g. "10:00"
    avoid_after: str | None = None   # soft
    prefer_later: bool = False
    locked_sections: list[str] = []
    excluded_courses: list[str] = []
    required_courses: list[str] = []  # student asked to include
    interest_boost_terms: list[str] = []
    deferred_courses: list[str] = []  # graduation-critical courses the student chose to defer
    accepted_tradeoffs: list[str] = []  # soft preferences the student explicitly gave up
    avoid_course_sets: list[list[str]] = []  # "show me different options" history


class GradPlanItem(BaseModel):
    course: str | None = None  # None = a requirement slot ("GenEd Science/Tech course"), never resolved by guessing
    label: str = ""
    credits: float | None = None
    notes: list[str] = []
    flags: list[str] = []  # winter_session, needs_confirmation
    include: bool = True   # the student's choice: schedule this course in that semester


class GradPlanTerm(BaseModel):
    term: str  # "Spring 2027"
    items: list[GradPlanItem] = []


class StudentProfile(BaseModel):
    id: str
    name: str
    is_demo: bool = True
    academic_year: str
    expected_graduation: str
    catalog_year: str | None
    planning_term: str
    program_ids: list[str]
    campus: str
    f1_status: Literal["yes", "no", "prefer_not"]
    interests_text: str
    career_interests: str = ""
    transcript: list[TranscriptItem]
    availability: list[AvailBlock]
    preferences: PlanningPreferences = Field(default_factory=PlanningPreferences)
    grad_plan: list[GradPlanTerm] = []  # the student's uploaded E-Graduation Plan, verified by the student

    def plan_courses(self, term_name: str) -> list[GradPlanItem]:
        """Courses the graduation plan selects for one semester (included, with a course code)."""
        for t in self.grad_plan:
            if t.term.lower() == term_name.lower():
                return [i for i in t.items if i.course and i.include]
        return []
