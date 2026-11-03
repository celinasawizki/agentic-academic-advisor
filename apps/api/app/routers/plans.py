from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.base import PlanContext
from app.agents.constraints import apply_changes, parse_change_request
from app.agents.review import review_sections
from app.core.auth import Principal, authorize_plan, authorize_student, get_principal
from app.core.db import get_db
from app.domain import AvailBlock, StudentProfile
from app.ingest.sections import components_by_course
from app.models import AgentExecution, AvailabilityBlock, PlanRun, Student
from app.optimizer import ScheduleModel
from app.orchestrator import PIPELINE, PlanBusy, create_plan, load_catalog, queue_agents, run_plan
from app.routers.students import AvailabilityIn
from app.rules import total_credits

router = APIRouter(prefix="/api/plans", tags=["plans"])
AGENT_META = {a.key: {"title": a.title, "responsibility": a.responsibility} for a in PIPELINE}
MAX_AVOID_SETS = 6


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
    section_ids: list[str] = Field(max_length=16)


class ResolveIn(BaseModel):
    relaxes: str = Field(max_length=200, description="Key of the constraint the student agrees to relax, from a resolution option")
    credits: int | None = Field(default=None, ge=0, le=24)


def persist_student(db: Session, plan: PlanRun, student: StudentProfile) -> None:
    """Save preference changes to the student's own record so later plans start from them.
    Fictional demo records are shared, so their changes stay scoped to this plan."""
    row = db.get(Student, plan.student_id)
    if row is None or row.is_demo:
        return
    p = student.preferences
    row.credit_target, row.credit_min, row.credit_max = p.credit_target, p.credit_min, p.credit_max
    row.preferences = p.model_dump(exclude={"credit_target", "credit_min", "credit_max"})
    db.query(AvailabilityBlock).filter_by(student_id=row.id).delete()
    for b in student.availability:
        db.add(AvailabilityBlock(student_id=row.id, day=b.day, start=b.start, end=b.end, kind=b.kind, label=b.label))


def _rerun(db: Session, plan: PlanRun, student: StudentProfile, bg: BackgroundTasks, history_entry: dict, start: str):
    try:
        queue_agents(db, plan, start, {"_student": student.model_dump(),
                                       "_history": [*plan.state.get("_history", []), history_entry]})
    except PlanBusy:
        raise HTTPException(409, "Planning is already running for this plan; wait for it to finish before making another change.")
    persist_student(db, plan, student)
    db.commit()
    bg.add_task(run_plan, plan.id, start)


@router.post("")
def create(body: CreatePlanIn, bg: BackgroundTasks, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    authorize_student(db, principal, body.student_id, "plan")
    plan = create_plan(db, body.student_id)
    queue_agents(db, plan, None)
    bg.add_task(run_plan, plan.id, None)
    return {"plan_id": plan.id}


@router.get("/{plan_id}")
def get_plan(plan_id: str, full: bool = True, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    """`full=false` returns agent status only (cheap enough to poll while agents run)."""
    plan = authorize_plan(db, principal, plan_id, "read")
    execs = db.query(AgentExecution).filter_by(plan_id=plan_id).order_by(AgentExecution.id).all()
    keep = None if full else {"_student", "_iteration", "_history", "_error"}
    state = {k: v for k, v in plan.state.items() if k != "_review_rejected_sets" and (keep is None or k in keep)}
    student = db.get(Student, plan.student_id)
    return {
        "id": plan.id, "status": plan.status, "term_id": plan.term_id, "student_id": plan.student_id,
        "is_demo": bool(student and student.is_demo), "iteration": plan.state.get("_iteration", 1),
        "agents": [{"id": e.id, "agent": e.agent, **AGENT_META.get(e.agent, {}), "iteration": e.iteration, "status": e.status,
                    "mode": e.mode, "summary": e.summary, "log": e.log if full else [], "sources": e.sources,
                    "decision": e.decision or {}, "error": e.error,
                    "started_at": e.started_at.isoformat() if e.started_at else None,
                    "finished_at": e.finished_at.isoformat() if e.finished_at else None} for e in execs],
        "state": state,
    }


@router.post("/{plan_id}/modify")
def modify(plan_id: str, body: ModifyIn, bg: BackgroundTasks, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    plan = authorize_plan(db, principal, plan_id, "modify")
    if plan.status == "running":
        raise HTTPException(409, "Planning is already running for this plan; wait for it to finish before making another change.")
    student = StudentProfile(**plan.state["_student"])
    current = sorted({s["course"] for o in plan.state.get("schedule_optimization", {}).get("options", []) for s in o["sections"]})
    changes, mode = parse_change_request(body.message, current)
    if not changes.changes:
        return {"applied": [], "assumptions": [], "unclear": changes.unclear, "mode": mode, "rerun": False}
    updated, applied, assumptions = apply_changes(student, changes)
    _rerun(db, plan, updated, bg, {"message": body.message, "applied": applied, "assumptions": assumptions, "mode": mode},
           "course_discovery")
    return {"applied": applied, "assumptions": assumptions, "unclear": changes.unclear, "mode": mode, "rerun": True}


@router.post("/{plan_id}/preferences")
def update_preferences(plan_id: str, body: PreferencesIn, bg: BackgroundTasks, db: Session = Depends(get_db),
                       principal: Principal = Depends(get_principal)):
    plan = authorize_plan(db, principal, plan_id, "modify")
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


@router.post("/{plan_id}/resolve")
def accept_resolution(plan_id: str, body: ResolveIn, bg: BackgroundTasks, db: Session = Depends(get_db),
                      principal: Principal = Depends(get_principal)):
    """Apply a tradeoff the student explicitly accepted from a solver-verified resolution.
    Hard availability is never relaxed here: the student must edit it themselves."""
    plan = authorize_plan(db, principal, plan_id, "modify")
    student = StudentProfile(**plan.state["_student"])
    p = student.preferences
    kind, _, target = body.relaxes.partition(":")
    pref_label = target.removeprefix("Preference: ") if target.startswith("Preference: ") else None
    if kind == "avail" and pref_label is not None:
        before = len(student.availability)
        student.availability = [b for b in student.availability if not (b.kind == "soft" and b.label == pref_label)]
        if len(student.availability) == before:
            raise HTTPException(422, f"No soft preference named '{pref_label}'")
        p.accepted_tradeoffs = [*p.accepted_tradeoffs, pref_label]
        applied = f"Accepted tradeoff: gave up '{pref_label}' for this term"
    elif kind == "avail":
        raise HTTPException(422, "This is a hard availability constraint. Change it yourself in the availability editor if your schedule allows.")
    elif kind == "must":
        p.deferred_courses = [*dict.fromkeys([*p.deferred_courses, target])]
        applied = f"Deferred {target} to a future term (graduation risk accepted)"
    elif kind == "req":
        p.required_courses = [c for c in p.required_courses if c != target]
        applied = f"No longer requiring {target}"
    elif kind == "lock":
        p.locked_sections = [s for s in p.locked_sections if s != target]
        applied = f"Unlocked {target}"
    elif kind == "credit_min" and body.credits is not None:
        p.credit_min = min(p.credit_min, body.credits)
        p.credit_target = body.credits
        applied = f"Credit load reduced to {body.credits}"
    elif kind == "f1":
        raise HTTPException(422, "Immigration requirements cannot be overridden by preferences. Contact ISSS.")
    else:
        raise HTTPException(422, "Unsupported resolution")
    _rerun(db, plan, student, bg, {"message": "Accepted a resolution option", "applied": [applied], "assumptions": [], "mode": "ui"},
           "course_discovery")
    return {"applied": [applied], "rerun": True}


@router.post("/{plan_id}/regenerate")
def regenerate(plan_id: str, bg: BackgroundTasks, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    """Ask for different combinations: the current options' course sets are avoided next run."""
    plan = authorize_plan(db, principal, plan_id, "modify")
    student = StudentProfile(**plan.state["_student"])
    current = [sorted({s["course"] for s in o["sections"]}) for o in plan.state.get("schedule_optimization", {}).get("options", [])]
    student.preferences.avoid_course_sets = [*student.preferences.avoid_course_sets, *current][-MAX_AVOID_SETS:]
    _rerun(db, plan, student, bg, {"message": "Show me different options", "applied": [f"Avoiding {len(current)} previous combination(s)"],
                                   "assumptions": [], "mode": "ui"}, "schedule_optimization")
    return {"applied": [f"Avoiding {len(current)} previous combination(s)"], "rerun": True}


@router.post("/{plan_id}/validate")
def validate(plan_id: str, body: ValidateIn, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    """Validates a manually edited schedule with exactly the checks the Academic Review Agent applies."""
    plan = authorize_plan(db, principal, plan_id, "read")
    if "course_discovery" not in plan.state:
        raise HTTPException(409, "Plan has not finished discovery yet")
    student = StudentProfile(**plan.state["_student"])
    catalog = load_catalog(db, plan.term_id, student.program_ids)
    by_id = {s.id: s for s in catalog.sections}
    unknown = [s for s in body.section_ids if s not in by_id]
    if unknown:
        raise HTTPException(422, f"Unknown sections for {catalog.term_name}: {unknown}")
    sections = [by_id[s] for s in dict.fromkeys(body.section_ids)]
    req_ids: dict[str, list[str]] = {}
    for e in plan.state["course_discovery"]["eligible_sections"]:
        req_ids.setdefault(e["course"], e["requirement_ids"])
    free = {c["course"] for c in plan.state.get("interest_matching", {}).get("interest_electives", [])}
    ctx = PlanContext(db=db, plan_id=plan_id, student=student, catalog=catalog, state=plan.state)
    checks = review_sections(ctx, sections, req_ids, components_by_course(catalog.sections), free)
    model = ScheduleModel([], catalog.courses, student.availability, student.preferences, {}, False, [])
    errors = [c for c in checks if not c["passed"] and c["severity"] == "error"]
    return {"valid": not errors, "checks": checks, "soft_violations": model.soft_violations(sections),
            "credits": total_credits(sections, catalog.courses)}
