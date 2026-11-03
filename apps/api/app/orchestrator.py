"""Multi-agent orchestration. Agents run as an explicit state machine over a
shared PlanRun.state; each step is persisted as an AgentExecution so the UI
shows real progress. The Review agent can reject options, which triggers a
bounded revision loop back through the optimizer."""

import logging
import traceback
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.adapters.catalog import DbCatalogAdapter
from app.adapters.course_search import SnapshotCourseSearchAdapter
from app.agents.base import Agent, Catalog, PlanContext
from app.agents.constraints import SchedulingConstraintsAgent
from app.agents.discovery import CourseDiscoveryAgent
from app.agents.explanation import StudentExplanationAgent
from app.agents.graduation import GraduationPlanningAgent
from app.agents.interests import InterestMatchingAgent
from app.agents.optimization import ScheduleOptimizationAgent
from app.agents.profile import AcademicProfileAgent
from app.agents.requirements import DegreeRequirementsAgent
from app.agents.review import AcademicReviewAgent
from app.core.config import settings
from app.core.db import SessionLocal
from app.domain import AvailBlock, PlanningPreferences, StudentProfile, TranscriptItem
from app.models import AgentExecution, PlanRun, Student

log = logging.getLogger(__name__)

PIPELINE: list[Agent] = [
    AcademicProfileAgent(), DegreeRequirementsAgent(), CourseDiscoveryAgent(), InterestMatchingAgent(),
    GraduationPlanningAgent(), SchedulingConstraintsAgent(), ScheduleOptimizationAgent(), AcademicReviewAgent(),
    StudentExplanationAgent(),
]
AGENT_KEYS = [a.key for a in PIPELINE]
MAX_REVISIONS = 1


def now() -> datetime:
    return datetime.now(timezone.utc)


def student_profile(db: Session, student_id: str) -> StudentProfile:
    s = db.get(Student, student_id)
    if s is None:
        raise KeyError(student_id)
    return StudentProfile(
        id=s.id, name=s.name, is_demo=s.is_demo, academic_year=s.academic_year, expected_graduation=s.expected_graduation,
        catalog_year=s.catalog_year, planning_term=s.planning_term, program_ids=s.program_ids, campus=s.campus,
        f1_status=s.f1_status, interests_text=" ".join(i.text for i in s.interests),
        transcript=[TranscriptItem(course=t.course_code, status=t.status, grade=t.grade, term=t.term, source=t.source,
                                   confidence=t.confidence) for t in s.transcript],
        availability=[AvailBlock(day=a.day, start=a.start, end=a.end, kind=a.kind, label=a.label) for a in s.availability],
        preferences=PlanningPreferences(credit_target=s.credit_target, credit_min=s.credit_min, credit_max=s.credit_max),
    )


def load_catalog(db: Session, term_id: str, program_ids: list[str]) -> Catalog:
    cs = SnapshotCourseSearchAdapter(db)
    cat = DbCatalogAdapter(db)
    term = cs.get_term(term_id)
    if term is None:
        raise ValueError(f"Unknown term {term_id}")
    return Catalog(term_id=term.id, term_name=term.name, courses=cs.get_courses(), sections=cs.search_sections(term_id),
                   requirements=cat.requirements(program_ids), programs=cat.programs(),
                   double_count_allowed=cat.double_count_allowed())


def create_plan(db: Session, student_id: str) -> PlanRun:
    profile = student_profile(db, student_id)
    plan = PlanRun(id=f"plan-{uuid.uuid4().hex[:10]}", student_id=student_id, term_id=profile.planning_term, status="pending",
                   state={"_student": profile.model_dump(), "_iteration": 0, "_history": []})
    db.add(plan)
    db.commit()
    return plan


def queue_agents(db: Session, plan: PlanRun, start_from: str | None) -> None:
    """Create pending AgentExecution rows up front so the UI shows the full workflow."""
    iteration = plan.state.get("_iteration", 0) + 1
    start = AGENT_KEYS.index(start_from) if start_from else 0
    for agent in PIPELINE[start:]:
        db.add(AgentExecution(plan_id=plan.id, agent=agent.key, iteration=iteration, status="pending"))
    for agent in PIPELINE[:start]:
        db.add(AgentExecution(plan_id=plan.id, agent=agent.key, iteration=iteration, status="skipped",
                              summary="Reused output from the previous iteration (inputs unchanged)."))
    plan.status = "running"
    plan.state = {**plan.state, "_iteration": iteration}
    db.commit()


def run_plan(plan_id: str, start_from: str | None = None) -> None:
    db = SessionLocal()
    try:
        _run(db, plan_id, start_from)
    except Exception:  # noqa: BLE001 - surface any failure to the UI instead of hanging
        log.exception("Plan %s failed", plan_id)
        plan = db.get(PlanRun, plan_id)
        if plan:
            plan.status = "failed"
            plan.state = {**plan.state, "_error": traceback.format_exc(limit=3)}
            db.commit()
    finally:
        db.close()


def _run(db: Session, plan_id: str, start_from: str | None) -> None:
    plan = db.get(PlanRun, plan_id)
    student = StudentProfile(**plan.state["_student"])
    state = {k: v for k, v in plan.state.items()}
    state["_llm_enabled"] = settings.llm_enabled
    state.pop("_review_rejected_sets", None)
    ctx = PlanContext(db=db, plan_id=plan_id, student=student,
                      catalog=load_catalog(db, plan.term_id, student.program_ids), state=state,
                      iteration=state["_iteration"])
    start = AGENT_KEYS.index(start_from) if start_from else 0
    for agent in PIPELINE[start:]:
        _execute(ctx, plan, agent)
        if agent.key == "academic_review":
            revisions = 0
            while ctx.state["academic_review"]["rejected"] and revisions < MAX_REVISIONS:
                revisions += 1
                for a in (PIPELINE[AGENT_KEYS.index("schedule_optimization")], PIPELINE[AGENT_KEYS.index("academic_review")]):
                    db.add(AgentExecution(plan_id=plan_id, agent=a.key, iteration=ctx.iteration, status="pending",
                                          summary=f"Revision {revisions}: requested by Academic Review Agent"))
                db.commit()
                for a in (PIPELINE[AGENT_KEYS.index("schedule_optimization")], PIPELINE[AGENT_KEYS.index("academic_review")]):
                    _execute(ctx, plan, a)
    plan.status = "complete"
    db.commit()


def _execute(ctx: PlanContext, plan: PlanRun, agent: Agent) -> None:
    db = ctx.db
    ex = (db.query(AgentExecution).filter_by(plan_id=plan.id, agent=agent.key, iteration=ctx.iteration, status="pending")
          .order_by(AgentExecution.id).first())
    ex.status, ex.started_at, ex.mode = "running", now(), "deterministic"
    db.commit()
    ctx._exec = ex
    try:
        output = agent.run(ctx)
    except Exception as e:
        ex.status, ex.finished_at, ex.error = "failed", now(), f"{type(e).__name__}: {e}"
        db.commit()
        raise
    ctx.state[agent.key] = output
    ex.status, ex.finished_at, ex.summary = "complete", now(), agent.summarize(output)
    plan.state = {k: v for k, v in ctx.state.items() if k != "_llm_enabled"}
    db.commit()
    ctx._exec = None
