import re
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.adapters.degree_audit import extract_text, parse_audit_text
from app.adapters.grad_plan import parse_grad_plan
from app.core.auth import Principal, authorize_student, get_principal, new_token
from app.core.config import settings
from app.core.db import get_db
from app.models import (StudentInterest, AcademicProgram, AcademicTerm, AdvisorReview, AgentExecution, Course, IntegrationStatus, PlanRun, ScheduleCourse,
                        SchedulingConstraint, ScheduleOption, Student, ValidationResult)
from app.orchestrator import student_profile
from app.seed import upsert_student

router = APIRouter(prefix="/api", tags=["students"])

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class TranscriptIn(BaseModel):
    course: str = Field(pattern=r"^[A-Z]{2,5} \d{4}$")
    status: Literal["completed", "in_progress", "transfer", "planned", "unverified"]
    grade: str | None = Field(default=None, max_length=4)
    term: str | None = Field(default=None, max_length=20)
    source: Literal["manual", "degree_audit_pdf", "demo"] = "manual"
    confidence: float = Field(default=1.0, ge=0, le=1)
    verified_by_student: bool = True


class AvailabilityIn(BaseModel):
    day: Literal["M", "T", "W", "R", "F", "S", "U"]
    start: str
    end: str
    kind: Literal["hard", "soft", "preferred"]
    label: str = Field(default="", max_length=80)

    @field_validator("start", "end")
    @classmethod
    def _time(cls, v: str) -> str:
        if not TIME_RE.match(v):
            raise ValueError("time must be HH:MM")
        return v


class GradPlanItemIn(BaseModel):
    course: str | None = Field(default=None, pattern=r"^[A-Z]{2,5} \d{4}$")
    label: str = Field(default="", max_length=200)
    credits: float | None = Field(default=None, ge=0, le=12)
    notes: list[str] = Field(default_factory=list, max_length=10)
    flags: list[Literal["winter_session", "needs_confirmation"]] = Field(default_factory=list)
    include: bool = True


class GradPlanTermIn(BaseModel):
    term: str = Field(pattern=r"^(Fall|Spring|Summer|Winter) \d{4}$")
    items: list[GradPlanItemIn] = Field(default_factory=list, max_length=15)


def plan_term_name(db: Session, term_id: str) -> str:
    t = db.get(AcademicTerm, term_id)
    return t.name if t else term_id


def require_term_courses(grad_plan: list[GradPlanTermIn], term_name: str) -> None:
    """Schedules are only proposed from the courses the student's graduation plan selects for the term."""
    for t in grad_plan:
        if t.term.lower() == term_name.lower():
            if any(i.course and i.include for i in t.items):
                return
            raise HTTPException(422, f"Your graduation plan has no courses selected for {term_name}. Include at least one course for that semester.")
    raise HTTPException(422, f"Upload your graduation plan first: it has no {term_name} semester, so there is nothing to schedule.")


class OnboardingIn(BaseModel):
    name: str = Field(max_length=120)
    academic_year: str = Field(max_length=20)
    expected_graduation: str = Field(pattern=r"^\d{4}-\d{2}$")
    catalog_year: str | None = Field(default=None, max_length=10)
    planning_term: str
    programs: list[str] = Field(min_length=1, max_length=8)
    campus: str = "Main"
    f1_status: Literal["yes", "no", "prefer_not"] = "prefer_not"
    interests_text: str = Field(default="", max_length=4000)
    career_interests: str = Field(default="", max_length=2000)
    interest_tags: list[str] = Field(default_factory=list, max_length=20)
    credit_target: int = Field(ge=1, le=24)
    credit_min: int = Field(ge=0, le=24)
    credit_max: int = Field(ge=1, le=24)
    transcript: list[TranscriptIn] = Field(default_factory=list, max_length=200)
    availability: list[AvailabilityIn] = Field(default_factory=list, max_length=200)
    grad_plan: list[GradPlanTermIn] = Field(default_factory=list, max_length=16)
    consent_to_process: bool


@router.get("/students/demo")
def demo_students(db: Session = Depends(get_db)):
    return [{"id": s.id, "name": s.name, "academic_year": s.academic_year} for s in db.query(Student).filter_by(is_demo=True).order_by(Student.id).all()]


@router.get("/students/{student_id}")
def get_student(student_id: str, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    authorize_student(db, principal, student_id, "read")
    return student_profile(db, student_id).model_dump()


@router.post("/students")
def create_student(body: OnboardingIn, db: Session = Depends(get_db)):
    if not body.consent_to_process:
        raise HTTPException(400, "Consent is required before academic records are processed.")
    if body.campus not in ("Main",):
        raise HTTPException(422, f"{body.campus} campus scheduling is not supported in this prototype yet. Choose Main Campus.")
    if not db.get(AcademicTerm, body.planning_term):
        raise HTTPException(422, "Unknown planning term")
    # Compare ids exactly: MySQL's case-insensitive collation would also find "CIS-BS" for "cis-bs".
    unknown = [p for p in dict.fromkeys(body.programs) if getattr(db.get(AcademicProgram, p), "id", None) != p]
    if unknown:  # otherwise the plan silently runs with no requirements for that program
        raise HTTPException(422, f"Unknown program(s): {', '.join(u[:120] for u in unknown)}")
    if not (body.credit_min <= body.credit_target <= body.credit_max):
        raise HTTPException(422, "Credit target must be within the acceptable range")
    if settings.require_grad_plan or body.grad_plan:
        require_term_courses(body.grad_plan, plan_term_name(db, body.planning_term))
    sid = f"stu-{uuid.uuid4().hex[:20]}"
    token, token_hash = new_token()
    st = upsert_student(db, {**body.model_dump(), "id": sid, "transcript": [t.model_dump() for t in body.transcript],
                             "availability": [a.model_dump() for a in body.availability], "access_token_hash": token_hash,
                             "grad_plan": [t.model_dump() for t in body.grad_plan]},
                        is_demo=False)
    if body.career_interests.strip():
        st.interests.append(StudentInterest(text=body.career_interests.strip(), tags=["career"]))
    db.commit()
    # The token is shown once; only its hash is stored. It stands in for Temple SSO in this prototype.
    return {"id": sid, "access_token": token}


@router.delete("/students/{student_id}")
def delete_student(student_id: str, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    existing = db.get(Student, student_id)
    if existing is not None and existing.is_demo:
        raise HTTPException(400, "Demo students cannot be deleted")
    s = authorize_student(db, principal, student_id, "delete")
    for p in db.query(PlanRun).filter_by(student_id=student_id).all():
        option_ids = [o.id for o in db.query(ScheduleOption).filter_by(plan_id=p.id).all()]
        db.query(ValidationResult).filter(ValidationResult.option_id.in_(option_ids)).delete(synchronize_session=False)
        db.query(ScheduleCourse).filter(ScheduleCourse.option_id.in_(option_ids)).delete(synchronize_session=False)
        for model in (ScheduleOption, AgentExecution, SchedulingConstraint, AdvisorReview, IntegrationStatus):
            db.query(model).filter_by(plan_id=p.id).delete(synchronize_session=False)
        db.delete(p)
    db.delete(s)
    db.commit()
    return {"deleted": student_id}


@router.post("/degree-audit/parse")
async def parse_degree_audit(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Parses in memory and returns rows for the student to verify. The file is
    never written to disk, logged, or sent to an external AI provider."""
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, "File too large (max 5 MB)")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(415, "Only PDF degree audits or unofficial transcripts are accepted")
    try:
        text = extract_text(data)
    except Exception:
        raise HTTPException(422, "Could not read this PDF")
    known = {c.code for c in db.query(Course.code).all()}
    result = parse_audit_text(text, known)
    if not result["entries"]:
        result["notes"].append("No course codes were found. You can add courses manually.")
    return result


@router.post("/grad-plan/parse")
async def parse_grad_plan_upload(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Parses an E-Graduation Plan PDF in memory and returns its semesters for the student to
    verify. Like degree audits, the file is never stored, logged, or sent to an AI provider."""
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, "File too large (max 5 MB)")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(415, "Upload your graduation plan as a PDF")
    try:
        result = parse_grad_plan(data, {c.code for c in db.query(Course.code).all()})
    except Exception:
        raise HTTPException(422, "Could not read this PDF")
    return result


class GradPlanIn(BaseModel):
    terms: list[GradPlanTermIn] = Field(max_length=16)


@router.put("/students/{student_id}/grad-plan")
def put_grad_plan(student_id: str, body: GradPlanIn, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    existing = db.get(Student, student_id)
    if existing is not None and existing.is_demo:
        raise HTTPException(400, "Demo students are shared and their records cannot be changed")
    s = authorize_student(db, principal, student_id, "modify")
    require_term_courses(body.terms, plan_term_name(db, s.planning_term))
    s.grad_plan = [t.model_dump() for t in body.terms]
    db.commit()
    return {"ok": True}
