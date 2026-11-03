"""Course search adapters.

Temple's public class search (Banner 9 Student Registration SSB) has no
documented open API. With the project owner's approval, scripts/import_sections.py
takes a one-time, rate-limited snapshot of a term into data/temple/sections-<term>.json;
the app only ever reads that committed snapshot and never calls Temple at runtime.
A live adapter should only be built against an endpoint Temple authorizes."""

from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.domain import CourseData, SectionData
from app.models import AcademicTerm, Course, CourseSection


class CourseSearchAdapter(ABC):
    name: str
    is_live: bool

    @abstractmethod
    def get_term(self, term_id: str) -> AcademicTerm | None: ...

    @abstractmethod
    def get_courses(self) -> dict[str, CourseData]: ...

    @abstractmethod
    def search_sections(self, term_id: str, course_codes: list[str] | None = None) -> list[SectionData]: ...


class SnapshotCourseSearchAdapter(CourseSearchAdapter):
    """Serves the committed course catalog and class-search snapshot from the database.
    Results are cached per dataset fingerprint because a plan reads thousands of rows."""

    name = "temple_snapshot"
    is_live = False
    _cache: dict[tuple, object] = {}

    def __init__(self, db: Session):
        self.db = db
        from app.models import ResearchSource
        marker = db.query(ResearchSource).filter_by(kind="dataset").first()
        self.version = marker.description if marker else "none"

    def get_term(self, term_id: str) -> AcademicTerm | None:
        return self.db.get(AcademicTerm, term_id)

    def get_courses(self) -> dict[str, CourseData]:
        key = ("courses", self.version)
        if key not in self._cache:
            self._cache[key] = {c.code: CourseData(code=c.code, title=c.title, credits=c.credits, description=c.description,
                                                   prereqs=c.prereqs, prereq_text=c.prereq_text or "", prereq_notes=c.prereq_notes or [],
                                                   attributes=c.attributes or [])
                                for c in self.db.query(Course).all()}
        return self._cache[key]  # type: ignore[return-value]

    def search_sections(self, term_id: str, course_codes: list[str] | None = None) -> list[SectionData]:
        key = ("sections", self.version, term_id)
        if key not in self._cache:
            self._cache[key] = [SectionData(id=s.id, course=s.course_code, term_id=s.term_id, section=s.section, crn=s.crn,
                                            instructor=s.instructor, campus=s.campus, modality=s.modality, location=s.location,
                                            meetings=s.meetings, seats_available=s.seats_available, credits=s.credits,
                                            schedule_type=s.schedule_type, linked=s.linked, attributes=s.attributes or [],
                                            data_source=s.data_source, retrieved_at=s.retrieved_at.isoformat())
                                for s in self.db.query(CourseSection).filter(CourseSection.term_id == term_id).all()]
        secs: list[SectionData] = self._cache[key]  # type: ignore[assignment]
        if course_codes:
            wanted = set(course_codes)
            return [s for s in secs if s.course in wanted]
        return secs


class TempleBannerCourseSearchAdapter(CourseSearchAdapter):
    """Placeholder for an authorized Temple course data integration. Not implemented:
    requires an endpoint or export Temple authorizes for this use."""

    name = "temple_banner"
    is_live = True

    def _unavailable(self):
        raise NotImplementedError("Temple course search integration requires authorized access; using demo fixtures.")

    def get_term(self, term_id):
        self._unavailable()

    def get_courses(self):
        self._unavailable()

    def search_sections(self, term_id, course_codes=None):
        self._unavailable()
