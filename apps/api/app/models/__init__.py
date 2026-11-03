"""Normalized persistence model. Every catalog-derived row carries provenance
(source, source_url, retrieved_at, catalog_year, verification_status)."""

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


class ResearchSource(Base):
    __tablename__ = "research_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))  # bulletin | course_search | degree_audit_upload | demo_fixture
    url: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(String(300))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    verification_status: Mapped[str] = mapped_column(String(30), default="demo_unverified")


class AcademicTerm(Base):
    __tablename__ = "academic_terms"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    start_date: Mapped[str] = mapped_column(String(10))
    end_date: Mapped[str] = mapped_column(String(10))


class AcademicProgram(Base):
    __tablename__ = "academic_programs"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    type: Mapped[str] = mapped_column(String(20))  # major | minor | certificate | gened
    college: Mapped[str] = mapped_column(String(120))
    catalog_year: Mapped[str | None] = mapped_column(String(10))
    supported: Mapped[bool] = mapped_column(Boolean, default=False)
    total_credit_hours: Mapped[str | None] = mapped_column(String(40))
    source_id: Mapped[int | None] = mapped_column(ForeignKey("research_sources.id"))
    source: Mapped[ResearchSource | None] = relationship()
    requirements: Mapped[list["ProgramRequirement"]] = relationship(back_populates="program", cascade="all, delete-orphan",
                                                                     order_by="ProgramRequirement.position")


class ProgramRequirement(Base):
    __tablename__ = "program_requirements"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    program_id: Mapped[str] = mapped_column(ForeignKey("academic_programs.id"))
    program: Mapped[AcademicProgram] = relationship(back_populates="requirements")
    position: Mapped[int] = mapped_column(Integer, default=0)
    group: Mapped[str] = mapped_column(String(300), default="")
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(10))  # count | credits | manual | note
    needed: Mapped[float] = mapped_column(Float)
    options: Mapped[list[list[str]]] = mapped_column(JSON, default=list)
    patterns: Mapped[list[dict]] = mapped_column(JSON, default=list)
    notes: Mapped[list[str]] = mapped_column(JSON, default=list)
    catalog_year: Mapped[str | None] = mapped_column(String(10))
    verification_status: Mapped[str] = mapped_column(String(30), default="parsed")
    source_id: Mapped[int | None] = mapped_column(ForeignKey("research_sources.id"))


class Course(Base):
    __tablename__ = "courses"
    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    subject: Mapped[str] = mapped_column(String(10), index=True)
    number: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    credits: Mapped[float] = mapped_column(Float)
    credits_max: Mapped[float | None] = mapped_column(Float)
    attributes: Mapped[list[str]] = mapped_column(JSON, default=list)
    prereqs: Mapped[list[list[str]]] = mapped_column(JSON, default=list)  # AND of OR-groups
    prereq_text: Mapped[str] = mapped_column(Text, default="")
    prereq_notes: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_url: Mapped[str | None] = mapped_column(String(300))
    source_id: Mapped[int | None] = mapped_column(ForeignKey("research_sources.id"))


class CourseSection(Base):
    __tablename__ = "course_sections"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)  # stable identifier: term-SUBJNUM-seq
    course_code: Mapped[str] = mapped_column(String(20), index=True)
    term_id: Mapped[str] = mapped_column(ForeignKey("academic_terms.id"), index=True)
    section: Mapped[str] = mapped_column(String(10))
    crn: Mapped[str] = mapped_column(String(20))
    title: Mapped[str | None] = mapped_column(String(300))
    instructor: Mapped[str] = mapped_column(String(300))
    campus: Mapped[str] = mapped_column(String(60))
    modality: Mapped[str] = mapped_column(String(20))  # in_person | online | hybrid | unknown
    instructional_method: Mapped[str | None] = mapped_column(String(80))
    schedule_type: Mapped[str | None] = mapped_column(String(80))
    location: Mapped[str] = mapped_column(String(160))
    meetings: Mapped[list[dict]] = mapped_column(JSON, default=list)
    credits: Mapped[float | None] = mapped_column(Float)
    seats_available: Mapped[int | None] = mapped_column(Integer)
    max_enrollment: Mapped[int | None] = mapped_column(Integer)
    linked: Mapped[bool] = mapped_column(Boolean, default=False)
    attributes: Mapped[list[str]] = mapped_column(JSON, default=list)
    data_source: Mapped[str] = mapped_column(String(40), default="temple_class_search_snapshot")
    source_id: Mapped[int | None] = mapped_column(ForeignKey("research_sources.id"))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Student(Base):
    __tablename__ = "students"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    academic_year: Mapped[str] = mapped_column(String(20))
    expected_graduation: Mapped[str] = mapped_column(String(7))
    catalog_year: Mapped[str | None] = mapped_column(String(10))
    planning_term: Mapped[str] = mapped_column(String(20))
    program_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    campus: Mapped[str] = mapped_column(String(40), default="Main")
    f1_status: Mapped[str] = mapped_column(String(20), default="prefer_not")
    credit_target: Mapped[int] = mapped_column(Integer, default=15)
    credit_min: Mapped[int] = mapped_column(Integer, default=12)
    credit_max: Mapped[int] = mapped_column(Integer, default=18)
    consent_to_process: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    transcript: Mapped[list["TranscriptEntry"]] = relationship(cascade="all, delete-orphan")
    interests: Mapped[list["StudentInterest"]] = relationship(cascade="all, delete-orphan")
    availability: Mapped[list["AvailabilityBlock"]] = relationship(cascade="all, delete-orphan")
    audits: Mapped[list["DegreeAudit"]] = relationship(cascade="all, delete-orphan")


class TranscriptEntry(Base):
    __tablename__ = "transcript_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"))
    course_code: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))  # completed | in_progress | transfer | planned | unverified
    grade: Mapped[str | None] = mapped_column(String(5))
    term: Mapped[str | None] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(30), default="manual")  # manual | degree_audit_pdf | demo
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    verified_by_student: Mapped[bool] = mapped_column(Boolean, default=False)


class DegreeAudit(Base):
    __tablename__ = "degree_audits"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"))
    filename: Mapped[str] = mapped_column(String(200))
    stored_path: Mapped[str | None] = mapped_column(String(400))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    extraction: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending_review")


class StudentInterest(Base):
    __tablename__ = "student_interests"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"))
    text: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)


class AvailabilityBlock(Base):
    __tablename__ = "availability_blocks"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"))
    day: Mapped[str] = mapped_column(String(1))  # M T W R F S U
    start: Mapped[str] = mapped_column(String(5))
    end: Mapped[str] = mapped_column(String(5))
    kind: Mapped[str] = mapped_column(String(10))  # hard | soft | preferred
    label: Mapped[str] = mapped_column(String(80), default="")


class PlanRun(Base):
    """Shared planning state for one orchestration run."""
    __tablename__ = "plan_runs"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"))
    term_id: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|running|complete|failed
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class SchedulingConstraint(Base):
    __tablename__ = "scheduling_constraints"
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plan_runs.id"))
    kind: Mapped[str] = mapped_column(String(20))  # hard | soft | academic | immigration
    code: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(String(300))
    params: Mapped[dict] = mapped_column(JSON, default=dict)


class AgentExecution(Base):
    __tablename__ = "agent_executions"
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plan_runs.id"))
    agent: Mapped[str] = mapped_column(String(60))
    iteration: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|running|complete|failed|skipped
    mode: Mapped[str] = mapped_column(String(20), default="deterministic")  # llm | deterministic | llm_fallback
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str] = mapped_column(Text, default="")
    log: Mapped[list[dict]] = mapped_column(JSON, default=list)
    sources: Mapped[list[dict]] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text)


class ScheduleOption(Base):
    __tablename__ = "schedule_options"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plan_runs.id"))
    label: Mapped[str] = mapped_column(String(60))
    strategy: Mapped[str] = mapped_column(String(30))
    rank: Mapped[int] = mapped_column(Integer)
    total_credits: Mapped[int] = mapped_column(Integer)
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    violated_soft: Mapped[list[dict]] = mapped_column(JSON, default=list)
    review_status: Mapped[str] = mapped_column(String(20), default="pending")  # approved|flagged|rejected|pending
    courses: Mapped[list["ScheduleCourse"]] = relationship(cascade="all, delete-orphan")


class ScheduleCourse(Base):
    __tablename__ = "schedule_courses"
    id: Mapped[int] = mapped_column(primary_key=True)
    option_id: Mapped[str] = mapped_column(ForeignKey("schedule_options.id"))
    section_id: Mapped[str] = mapped_column(String(60))
    course_code: Mapped[str] = mapped_column(String(20))
    requirement_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    interest_score: Mapped[float] = mapped_column(Float, default=0)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)


class ValidationResult(Base):
    __tablename__ = "validation_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    option_id: Mapped[str] = mapped_column(ForeignKey("schedule_options.id"))
    check: Mapped[str] = mapped_column(String(60))
    passed: Mapped[bool] = mapped_column(Boolean)
    severity: Mapped[str] = mapped_column(String(10))  # info|warning|error
    detail: Mapped[str] = mapped_column(Text)


class AdvisorReview(Base):
    __tablename__ = "advisor_reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plan_runs.id"))
    advisor_name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20))  # needs_review | approved | changes_requested
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class IntegrationStatus(Base):
    __tablename__ = "integration_status"
    id: Mapped[int] = mapped_column(primary_key=True)
    adapter: Mapped[str] = mapped_column(String(60))
    operation: Mapped[str] = mapped_column(String(60))
    plan_id: Mapped[str | None] = mapped_column(String(40))
    option_id: Mapped[str | None] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20))
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
