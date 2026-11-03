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
        m = re.search(r"(?i)minimum grade of ([A-D][+-]?)\b", self.prereq_text or "")
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
    kind: Literal["count", "credits", "manual", "note"]
    needed: float
    options: list[list[str]] = []
    patterns: list[dict] = []
    notes: list[str] = []
    catalog_year: str | None = None
    verification_status: str
    source_url: str | None = None

    @property
    def courses(self) -> list[str]:
        return [c for opt in self.options for c in opt]

    def pattern_matches(self, course: "CourseData", section_attrs: list[str] | None = None) -> bool:
        for p in self.patterns:
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
