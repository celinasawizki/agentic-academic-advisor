from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.adapters.tuportal import MockTUportalAdapter
from app.core.config import settings
from app.core.db import get_db
from app.models import IntegrationStatus, PlanRun, ScheduleOption

router = APIRouter(prefix="/api/integration", tags=["integration"])


class DraftIn(BaseModel):
    plan_id: str
    option_id: str


@router.get("/status")
def status():
    return {
        "tuportal": {"adapter": "MockTUportalAdapter", "mock": True, "live": False,
                     "note": "No authorized TUportal test environment. Drafts are saved to a local mock store; nobody is registered."},
        "course_search": {"adapter": "DemoFixtureCourseSearchAdapter", "live": False,
                          "note": "Temple course search has no documented public API; sections are labeled demo fixtures."},
        "degree_audit": {"adapter": "PDF upload parser", "live": False,
                         "note": "Degree Audit requires university authentication; students upload a PDF which is parsed locally."},
        "requirements": {"adapter": "DbCatalogAdapter", "live": False, "note": "Requirement fixtures pending bulletin verification."},
        "llm": {"enabled": settings.llm_enabled, "model": settings.anthropic_model if settings.llm_enabled else None,
                "student_records_sent": settings.llm_may_receive_student_records},
    }


@router.post("/tuportal/drafts")
def save_draft(body: DraftIn, db: Session = Depends(get_db)):
    plan = db.get(PlanRun, body.plan_id)
    opt = db.get(ScheduleOption, body.option_id)
    if not plan or not opt or opt.plan_id != plan.id:
        raise HTTPException(404, "Schedule option not found")
    if opt.review_status == "rejected":
        raise HTTPException(409, "This schedule was rejected by the Academic Review Agent and cannot be exported.")
    adapter = MockTUportalAdapter(db)
    sections = {s["id"]: s for o in plan.state["schedule_optimization"]["options"] for s in o["sections"]}
    crns = [sections[c.section_id]["crn"] for c in opt.courses if c.section_id in sections]
    draft = adapter.create_draft_schedule(plan.student_id, plan.term_id, plan.id, opt.id, crns)
    validation = adapter.validate_draft_schedule(draft["draft_id"])
    return {"draft": draft, "validation": validation, "mock": True,
            "notice": "MOCK: saved to a simulated planning environment. This is not TUportal and you are NOT registered."}


@router.get("/tuportal/drafts")
def list_drafts(plan_id: str, db: Session = Depends(get_db)):
    rows = db.query(IntegrationStatus).filter_by(plan_id=plan_id, operation="create_draft_schedule").all()
    return [{"draft_id": r.payload["draft_id"], "option_id": r.option_id, "crns": r.payload["crns"],
             "created_at": r.created_at.isoformat(), "mock": r.is_mock} for r in rows]
