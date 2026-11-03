from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import AdvisorReview, PlanRun, Student

router = APIRouter(prefix="/api/advisor", tags=["advisor"])


def require_advisor(x_demo_role: str | None = Header(default=None)) -> None:
    """Demo-only role gate. A real deployment must use Temple SSO and
    advisor-student assignment checks before exposing any student data."""
    if x_demo_role != "advisor":
        raise HTTPException(403, "Advisor role required")


class ReviewIn(BaseModel):
    plan_id: str
    status: Literal["needs_review", "approved", "changes_requested"]
    note: str = Field(default="", max_length=2000)
    advisor_name: str = Field(default="Demo Advisor", max_length=120)


@router.get("/overview", dependencies=[Depends(require_advisor)])
def overview(db: Session = Depends(get_db)):
    out = []
    for s in db.query(Student).filter_by(is_demo=True).all():
        plan = db.query(PlanRun).filter_by(student_id=s.id, status="complete").order_by(PlanRun.created_at.desc()).first()
        item = {"student_id": s.id, "name": s.name, "academic_year": s.academic_year, "programs": s.program_ids,
                "expected_graduation": s.expected_graduation, "f1": s.f1_status == "yes", "plan_id": None}
        if plan:
            st = plan.state
            reviews = st.get("academic_review", {}).get("reviews", {})
            ideal = st.get("schedule_optimization", {}).get("ideal_analysis", {})
            adv = db.query(AdvisorReview).filter_by(plan_id=plan.id).order_by(AdvisorReview.created_at.desc()).first()
            item.update({
                "plan_id": plan.id,
                "remaining_requirements": [{"id": r["id"], "name": r["name"], "program": r["program_name"], "needed": r["remaining_needed"]}
                                           for r in st.get("degree_requirements", {}).get("remaining", [])],
                "conflicts": [g["description"] for g in ideal.get("conflict_set", [])],
                "risks": st.get("graduation_planning", {}).get("risks", []),
                "critical_courses": [c["course"] for c in st.get("graduation_planning", {}).get("critical_courses", [])],
                "options": [{"id": o["id"], "label": o["label"], "credits": o["credits"],
                             "courses": [x["course"] for x in o["sections"]],
                             "review_status": reviews.get(o["id"], {}).get("status")}
                            for o in st.get("schedule_optimization", {}).get("options", [])],
                "explanation": st.get("student_explanation", {}).get("headline"),
                "ai_summary": st.get("student_explanation", {}).get("overall_ai_summary"),
                "needs_review": (not ideal.get("perfect_exists", True)) or any(r.get("warnings") for r in reviews.values()),
                "advisor_review": {"status": adv.status, "note": adv.note, "by": adv.advisor_name} if adv else None,
            })
        out.append(item)
    return out


@router.post("/reviews", dependencies=[Depends(require_advisor)])
def add_review(body: ReviewIn, db: Session = Depends(get_db)):
    if not db.get(PlanRun, body.plan_id):
        raise HTTPException(404, "Plan not found")
    db.add(AdvisorReview(plan_id=body.plan_id, advisor_name=body.advisor_name, status=body.status, note=body.note))
    db.commit()
    return {"ok": True}
