import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import Base, engine
from app.models import (AcademicProgram, AcademicTerm, AvailabilityBlock, Course, CourseSection, ProgramRequirement,
                        ResearchSource, Student, StudentInterest, TranscriptEntry)


def init_db() -> None:
    Base.metadata.create_all(engine)


def seed(db: Session) -> None:
    if db.query(Course).count():
        return
    d = settings.data_dir
    progs = json.loads((d / "programs.json").read_text())
    cat = json.loads((d / "courses.json").read_text())
    studs = json.loads((d / "students.json").read_text())

    for p in progs["programs"]:
        src = None
        if p.get("source_url"):
            src = ResearchSource(kind="bulletin", url=p["source_url"], description=f"{p['name']} {p['type']} requirements (demo fixture)",
                                 retrieved_at=datetime.fromisoformat(p["retrieved_at"].replace("Z", "+00:00")),
                                 verification_status="demo_unverified")
            db.add(src)
            db.flush()
        prog = AcademicProgram(id=p["id"], name=p["name"], type=p["type"], college=p["college"], catalog_year=p.get("catalog_year"),
                               supported=p["supported"], source_id=src.id if src else None)
        for r in p["requirements"]:
            prog.requirements.append(ProgramRequirement(id=r["id"], name=r["name"], rule=r["rule"], choose_count=r.get("choose_count"),
                                                        courses=r["courses"], category=r["category"], catalog_year=p["catalog_year"],
                                                        source_id=src.id if src else None))
        db.add(prog)

    csrc = ResearchSource(kind="demo_fixture", url=None, description=f"Demo course/section fixture for {cat['term']['name']}")
    db.add(csrc)
    db.flush()
    t = cat["term"]
    db.add(AcademicTerm(id=t["id"], name=t["name"], start_date=t["start"], end_date=t["end"]))
    for c in cat["courses"]:
        subj, num = c["code"].split()
        db.add(Course(code=c["code"], subject=subj, number=num, title=c["title"], description=c["description"],
                      credits=c["credits"], prereqs=c["prereqs"], source_id=csrc.id))
    db.flush()
    for s in cat["sections"]:
        db.add(CourseSection(id=s["id"], course_code=s["course"], term_id=t["id"], section=s["section"], crn=s["crn"],
                             instructor=s["instructor"], campus=s["campus"], modality=s["modality"], location=s["location"],
                             meetings=s["meetings"], seats_available=s.get("seats_available"), data_source="demo_fixture",
                             source_id=csrc.id))
    for s in studs["students"]:
        upsert_student(db, s, is_demo=True)
    db.commit()


def upsert_student(db: Session, s: dict, is_demo: bool) -> Student:
    existing = db.get(Student, s["id"])
    if existing:
        db.delete(existing)
        db.flush()
    st = Student(id=s["id"], name=s["name"], is_demo=is_demo, academic_year=s["academic_year"],
                 expected_graduation=s["expected_graduation"], catalog_year=s.get("catalog_year"),
                 planning_term=s["planning_term"], program_ids=s["programs"], campus=s["campus"], f1_status=s["f1_status"],
                 credit_target=s["credit_target"], credit_min=s["credit_min"], credit_max=s["credit_max"],
                 consent_to_process=s.get("consent_to_process", is_demo))
    st.transcript = [TranscriptEntry(course_code=t["course"], status=t["status"], grade=t.get("grade"), term=t.get("term"),
                                     source=t.get("source", "demo" if is_demo else "manual"), confidence=t.get("confidence", 1.0),
                                     verified_by_student=t.get("verified_by_student", is_demo)) for t in s["transcript"]]
    st.interests = [StudentInterest(text=s.get("interests_text", ""), tags=s.get("interest_tags", []))]
    st.availability = [AvailabilityBlock(day=a["day"], start=a["start"], end=a["end"], kind=a["kind"], label=a.get("label", ""))
                       for a in s["availability"]]
    db.add(st)
    db.flush()
    return st
