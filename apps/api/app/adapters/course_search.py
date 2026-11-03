"""Course search adapters.

Temple's public class search (Banner 9 Student Registration SSB at
prd-xereg.temple.edu/StudentRegistrationSsb/ssb/courseSearch) is a browser
application backed by session-bound JSON endpoints. It does not publish a
documented open API, so this prototype does not call it. A real adapter should
only be built against an endpoint or data export Temple authorizes."""

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


class DemoFixtureCourseSearchAdapter(CourseSearchAdapter):
    """Serves the clearly labeled demo fixture ingested into the database."""

    name = "demo_fixture"
    is_live = False

    def __init__(self, db: Session):
        self.db = db

    def get_term(self, term_id: str) -> AcademicTerm | None:
        return self.db.get(AcademicTerm, term_id)

    def get_courses(self) -> dict[str, CourseData]:
        return {c.code: CourseData(code=c.code, title=c.title, credits=c.credits, description=c.description, prereqs=c.prereqs)
                for c in self.db.query(Course).all()}

    def search_sections(self, term_id: str, course_codes: list[str] | None = None) -> list[SectionData]:
        q = self.db.query(CourseSection).filter(CourseSection.term_id == term_id)
        if course_codes:
            q = q.filter(CourseSection.course_code.in_(course_codes))
        return [SectionData(id=s.id, course=s.course_code, term_id=s.term_id, section=s.section, crn=s.crn,
                            instructor=s.instructor, campus=s.campus, modality=s.modality, location=s.location,
                            meetings=s.meetings, seats_available=s.seats_available, data_source=s.data_source,
                            retrieved_at=s.retrieved_at.isoformat()) for s in q.all()]


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
