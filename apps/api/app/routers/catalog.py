from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.adapters.catalog import DbCatalogAdapter
from app.core.db import get_db
from app.ingest.school import LAYER_TYPES
from app.models import AcademicTerm, Course

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("/programs")
def programs(db: Session = Depends(get_db)):
    progs = [p for p in DbCatalogAdapter(db).programs().values() if p["type"] not in LAYER_TYPES]  # layers apply automatically
    return sorted(progs, key=lambda p: (not p["supported"], p["type"], p["name"]))


@router.get("/terms")
def terms(db: Session = Depends(get_db)):
    return [{"id": t.id, "name": t.name, "start": t.start_date, "end": t.end_date} for t in db.query(AcademicTerm).all()]


@router.get("/courses")
def courses(db: Session = Depends(get_db)):
    return [{"code": c.code, "title": c.title, "credits": c.credits} for c in db.query(Course).order_by(Course.code).all()]
