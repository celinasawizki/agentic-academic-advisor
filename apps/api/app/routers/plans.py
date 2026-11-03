from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.base import PlanContext
from app.agents.constraints import apply_changes, parse_change_request
from app.agents.review import review_sections
from app.core.db import get_db
from app.domain import AvailBlock, SectionData, StudentProfile
from app.models import AgentExecution, PlanRun, Student
from app.optimizer import ScheduleModel
from app.orchestrator import PIPELINE, create_plan, load_catalog, queue_agents, run_plan
from app.routers.students import AvailabilityIn

router = APIRouter(prefix="/api/plans", tags=["plans"])
AGENT_META = {a.key: {"title": a.title, "responsibility": a.responsibility} for a in PIPELINE}


class CreatePlanIn(BaseModel):
    student_id: str


class ModifyIn(BaseModel):
    message: str = Field(min_length=2, max_length=500)


class PreferencesIn(BaseModel):
    credit_target: int | None = Field(default=None, ge=1, le=24)
    credit_min: int | None = Field(default=None, ge=0, le=24)
    credit_max: int | None = Field(default=None, ge=1, le=24)
    locked_sections: list[str] | None = None
    excluded_courses: list[str] | None = None
    required_courses: list[str] | None = None
    availability: list[AvailabilityIn] | None = None


class ValidateIn(BaseModel):
    section_ids: list[str] = Field(max_length=10)


def _get_plan(db: Session, plan_id: str) -> PlanRun:
    plan = db.get(PlanRun, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    return plan


def _rerun(db: Session, plan: PlanRun, student: StudentProfile, bg: BackgroundTasks, history_entry: dict, start: str):
    if plan.status == "running":
        raise HTTPException(409, "Planning is already running; wait for it to finish.")
    plan.state = {**plan.state, "_student": student.model_dump(), "_history": [*plan.state.get("_history", []), history_entry]}
    db.commit()
    queue_agents(db, plan, start)
    bg.add_task(run_plan, plan.id, start)


@router.post("")
def create(body: CreatePlanIn, bg: BackgroundTasks, db: Session = Depends(get_db)):
    if not db.get(Student, body.student_id):
        raise HTTPException(404, "Student not found")
    plan = create_plan(db, body.student_id)
    queue_agents(db, plan, None)
    bg.add_task(run_plan, plan.id, None)
    return {"plan_id": plan.id}


@router.get("/{plan_id}")
def get_plan(plan_id: str, full: bool = True, db: Session = Depends(get_db)):
    """`full=false` returns agent status only (cheap enough to poll while agents run)."""
    plan = _get_plan(db, plan_id)
    execs = db.query(AgentExecution).filter_by(plan_id=plan_id).order_by(AgentExecution.id).all()
    keep = None if full else {"_student", "_iteration", "_history", "_error"}
    state = {k: v for k, v in plan.state.items() if k != "_review_rejected_sets" and (keep is None or k in keep)}
    return {
        "id": plan.id, "status": plan.status, "term_id": plan.term_id, "student_id": plan.student_id,
        "iteration": plan.state.get("_iteration", 1),
        "agents": [{"id": e.id, "agent": e.agent, **AGENT_META.get(e.agent, {}), "iteration": e.iteration, "status": e.status,
                    "mode": e.mode, "summary": e.summary, "log": e.log, "sources": e.sources, "error": e.error,
                    "started_at": e.started_at.isoformat() if e.started_at else None,
                    "finished_at": e.finished_at.isoformat() if e.finished_at else None} for e in execs],
        "state": state,
    }


@router.post("/{plan_id}/modify")
def modify(plan_id: str, body: ModifyIn, bg: BackgroundTasks, db: Session = Depends(get_db)):
    plan = _get_plan(db, plan_id)
    student = StudentProfile(**plan.state["_student"])
    current = sorted({s["course"] for o in plan.state.get("schedule_optimization", {}).get("options", []) for s in o["sections"]})
    changes, mode = parse_change_request(body.message, current)
    if not changes.changes:
        return {"applied": [], "assumptions": [], "unclear": changes.unclear, "mode": mode, "rerun": False}
    updated, applied, assumptions = apply_changes(student, changes)
    start = "course_discovery"
    _rerun(db, plan, updated, bg, {"message": body.message, "applied": applied, "assumptions": assumptions, "mode": mode}, start)
    return {"applied": applied, "assumptions": assumptions, "unclear": changes.unclear, "mode": mode, "rerun": True}


@router.post("/{plan_id}/preferences")
def update_preferences(plan_id: str, body: PreferencesIn, bg: BackgroundTasks, db: Session = Depends(get_db)):
    plan = _get_plan(db, plan_id)
    student = StudentProfile(**plan.state["_student"])
    p = student.preferences
    applied = []
    for field in ("credit_target", "credit_min", "credit_max", "locked_sections", "excluded_courses", "required_courses"):
        val = getattr(body, field)
        if val is not None:
            setattr(p, field, val)
            applied.append(f"{field} = {val}")
    if not (p.credit_min <= p.credit_target <= p.credit_max):
        raise HTTPException(422, "Credit target must be within the acceptable range")
    if body.availability is not None:
        student.availability = [AvailBlock(**a.model_dump()) for a in body.availability]
        applied.append(f"availability updated ({len(body.availability)} blocks)")
    _rerun(db, plan, student, bg, {"message": "Edited in schedule builder", "applied": applied, "assumptions": [], "mode": "ui"},
           "course_discovery")
    return {"applied": applied, "rerun": True}


@router.post("/{plan_id}/validate")
def validate(plan_id: str, body: ValidateIn, db: Session = Depends(get_db)):
    """Validates a manually edited schedule (e.g. after swapping a section) with
    the same deterministic checks the Academic Review Agent uses."""
    plan = _get_plan(db, plan_id)
    if "course_discovery" not in plan.state:
        raise HTTPException(409, "Plan has not finished discovery yet")
    student = StudentProfile(**plan.state["_student"])
    catalog = load_catalog(db, plan.term_id, student.program_ids)
    by_id = {s.id: s for s in catalog.sections}
    unknown = [s for s in body.section_ids if s not in by_id]
    if unknown:
        raise HTTPException(422, f"Unknown sections: {unknown}")
    sections = [by_id[s] for s in body.section_ids]
    elig = {e["course"]: e["requirement_ids"] for e in plan.state["course_discovery"]["eligible_sections"]}
    ctx = PlanContext(db=db, plan_id=plan_id, student=student, catalog=catalog, state=plan.state)
    checks = review_sections(ctx, sections, elig)
    model = ScheduleModel([], catalog.courses, student.availability, student.preferences, {}, False, [])
    errors = [c for c in checks if not c["passed"] and c["severity"] == "error"]
    return {"valid": not errors, "checks": checks, "soft_violations": model.soft_violations(sections),
            "credits": sum(catalog.courses[s.course].credits for s in sections)}
