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
    data_source: str
    retrieved_at: str


class CourseData(BaseModel):
    code: str
    title: str
    credits: int
    description: str
    prereqs: list[list[str]] = []


class RequirementData(BaseModel):
    id: str
    program_id: str
    program_name: str
    program_type: str
    name: str
    rule: Literal["all", "choose"]
    choose_count: int | None = None
    courses: list[str]
    category: str
    catalog_year: str
    verification_status: str
    source_url: str | None = None

    @property
    def needed(self) -> int:
        return len(self.courses) if self.rule == "all" else (self.choose_count or 1)


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
    transcript: list[TranscriptItem]
    availability: list[AvailBlock]
    preferences: PlanningPreferences = Field(default_factory=PlanningPreferences)
