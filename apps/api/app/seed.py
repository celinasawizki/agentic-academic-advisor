"""Loads the catalog dataset (programs, courses, sections, fictional students)
into the database. The catalog is reloaded whenever the dataset files change;
students and plans are preserved."""

import hashlib
import html as htmllib
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, insert, inspect, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import Base, engine
from app.ingest.sections import modality
from app.models import (AcademicProgram, AcademicTerm, AvailabilityBlock, Course, CourseSection, ProgramRequirement,
                        ResearchSource, Student, StudentInterest, TranscriptEntry)

SEASON = {"03": "Spring", "36": "Fall", "20": "Summer I", "26": "Summer II"}


def init_db() -> None:
    Base.metadata.create_all(engine)
    _add_missing_columns()


def _add_missing_columns() -> None:
    """Additive-only migration for prototype databases: add new nullable columns."""
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existing:
                    conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN "{col.name}" {col.type.compile(engine.dialect)}'))


def term_name(code: str) -> str:
    return f"{SEASON.get(code[4:], code[4:])} {code[:4]}"


CATALOG_SCHEMA_VERSION = "3"


def _fingerprint(files: list[Path]) -> str:
    h = hashlib.sha1(CATALOG_SCHEMA_VERSION.encode())
    for f in sorted(files):
        st = f.stat()
        h.update(f"{f.name}:{st.st_size}:{int(st.st_mtime)}".encode())
    return h.hexdigest()


def _dt(s: str | None) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else datetime.now(timezone.utc)


def dataset_files(d: Path) -> list[Path]:
    return [d / "programs.json", d / "courses.json", *sorted(d.glob("sections-*.json")), d / "students.json"]


def seed(db: Session, data_dir: Path | None = None) -> None:
    d = data_dir or settings.data_dir
    files = [f for f in dataset_files(d) if f.exists()]
    fp = _fingerprint(files)
    marker = db.query(ResearchSource).filter_by(kind="dataset").first()
    if marker and marker.description == fp and db.query(Course).count():
        return
    load_catalog(db, d)
    if marker:
        marker.description = fp
    else:
        db.add(ResearchSource(kind="dataset", url=None, description=fp, verification_status="n/a"))
    students = json.loads((d / "students.json").read_text()) if (d / "students.json").exists() else {"students": []}
    for s in students["students"]:
        upsert_student(db, s, is_demo=True)
    db.commit()


def load_catalog(db: Session, d: Path) -> None:
    for model in (ProgramRequirement, AcademicProgram, CourseSection, Course, AcademicTerm):
        db.execute(delete(model))
    db.query(ResearchSource).filter(ResearchSource.kind != "dataset").delete()
    db.flush()

    progs = json.loads((d / "programs.json").read_text())
    cat = json.loads((d / "courses.json").read_text())
    for p in progs["programs"]:
        src = ResearchSource(kind="bulletin", url=p.get("source_url"), description=f"{p['name']} requirements",
                             retrieved_at=_dt(p.get("retrieved_at")),
                             verification_status=p.get("verification_status", "parsed_pending_verification"))
        db.add(src)
        db.flush()
        db.add(AcademicProgram(id=p["id"], name=p["name"], type=p["type"], college=p["college"], catalog_year=p.get("catalog_year"),
                               supported=p.get("supported", True), total_credit_hours=", ".join(p.get("total_credit_hours") or []) or None,
                               layers=p.get("layers", []), min_grade=p.get("min_grade"), source_id=src.id))
        db.flush()
        rows = [{"id": r["id"], "program_id": p["id"], "position": i, "group": r.get("group", ""), "name": r["name"], "kind": r["kind"],
                 "needed": r["needed"], "options": r.get("options", []), "patterns": r.get("patterns", []), "notes": r.get("notes", []),
                 "catalog_year": p.get("catalog_year"), "verification_status": r.get("verification_status", "parsed"),
                 "evidence": r.get("evidence"), "source_id": src.id}
                for i, r in enumerate(p["requirements"])]
        if rows:
            db.execute(insert(ProgramRequirement), rows)

    csrc = ResearchSource(kind="bulletin_courses", url=cat.get("_meta", {}).get("base_url"),
                          description=cat.get("_meta", {}).get("source", "course catalog"), retrieved_at=_dt(cat.get("_meta", {}).get("generated_at")))
    db.add(csrc)
    db.flush()
    db.execute(insert(Course), [{
        "code": c["code"], "subject": c["code"].split()[0], "number": c["code"].split()[1], "title": c["title"],
        "description": c.get("description", ""), "credits": c["credits"], "credits_max": c.get("credits_max"),
        "attributes": c.get("attributes", []), "prereqs": c.get("prereqs", []), "prereq_text": c.get("prereq_text", ""),
        "prereq_notes": c.get("prereq_notes", []), "source_url": c.get("source_url"), "source_id": csrc.id} for c in cat["courses"]])

    for f in sorted(d.glob("sections-*.json")):
        snap = json.loads(f.read_text())
        meta = snap.get("_meta", {})
        term = meta.get("term") or f.stem.split("-", 1)[1]
        db.add(AcademicTerm(id=term, name=term_name(term), start_date=meta.get("start_date", ""), end_date=meta.get("end_date", "")))
        ssrc = ResearchSource(kind=meta.get("kind", "course_search"), url=meta.get("url"), description=meta.get("source", "sections"),
                              retrieved_at=_dt(meta.get("retrieved_at")), verification_status=meta.get("verification_status", "snapshot"))
        db.add(ssrc)
        db.flush()
        retrieved = _dt(meta.get("retrieved_at"))
        seen: set[str] = set()
        for sec in snap["sections"]:
            if sec["id"] in seen:
                sec["id"] = f"{sec['id']}-{sec['crn']}"
            seen.add(sec["id"])
            if sec.get("instructional_method"):
                sec["modality"] = modality(sec["instructional_method"], None)
            for k in ("campus", "title", "instructor"):
                if isinstance(sec.get(k), str):
                    sec[k] = htmllib.unescape(sec[k])
        db.execute(insert(CourseSection), [{
            "id": s["id"], "course_code": s["course"], "term_id": term, "section": s["section"], "crn": s["crn"],
            "title": s.get("title"), "instructor": s.get("instructor") or "Staff", "campus": s.get("campus") or "Unknown",
            "modality": s.get("modality", "unknown"), "instructional_method": s.get("instructional_method"),
            "schedule_type": s.get("schedule_type"),
            "location": s.get("location") or ", ".join(dict.fromkeys(f"{m.get('building') or ''} {(m.get('room') or '').lstrip('0')}".strip() for m in s.get("meetings", []) if m.get("building"))) or ("Online" if s.get("modality") == "online" else "TBA"),
            "meetings": [{"days": m["days"], "start": m["start"], "end": m["end"]} for m in s.get("meetings", [])],
            "credits": s.get("credits"), "credits_max": s.get("credits_high"), "seats_available": s.get("seats_available"), "max_enrollment": s.get("max_enrollment"),
            "linked": bool(s.get("linked")), "attributes": s.get("attributes", []),
            "data_source": meta.get("data_source", "temple_class_search_snapshot"), "source_id": ssrc.id, "retrieved_at": retrieved,
        } for s in snap["sections"]])
    db.flush()


def upsert_student(db: Session, s: dict, is_demo: bool) -> Student:
    existing = db.get(Student, s["id"])
    if existing:
        db.delete(existing)
        db.flush()
    st = Student(id=s["id"], name=s["name"], is_demo=is_demo, academic_year=s["academic_year"],
                 expected_graduation=s["expected_graduation"], catalog_year=s.get("catalog_year"),
                 planning_term=s["planning_term"], program_ids=s["programs"], campus=s["campus"], f1_status=s["f1_status"],
                 credit_target=s["credit_target"], credit_min=s["credit_min"], credit_max=s["credit_max"],
                 consent_to_process=s.get("consent_to_process", is_demo), access_token_hash=s.get("access_token_hash"),
                 preferences=s.get("preferences") or {}, grad_plan=s.get("grad_plan") or [])
    st.transcript = [TranscriptEntry(course_code=t["course"], status=t["status"], grade=t.get("grade"), term=t.get("term"),
                                     source=t.get("source", "demo" if is_demo else "manual"), confidence=t.get("confidence", 1.0),
                                     verified_by_student=t.get("verified_by_student", is_demo)) for t in s["transcript"]]
    st.interests = [StudentInterest(text=s.get("interests_text", ""), tags=s.get("interest_tags", []))]
    st.availability = [AvailabilityBlock(day=a["day"], start=a["start"], end=a["end"], kind=a["kind"], label=a.get("label", ""))
                       for a in s["availability"]]
    db.add(st)
    db.flush()
    return st
