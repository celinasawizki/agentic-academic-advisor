"""TUportal integration boundary. Only a MOCK adapter exists; it never contacts
Temple systems and never registers anyone for classes. A real adapter can be
swapped in once authorized test-environment credentials and API docs exist."""

import uuid
from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.models import IntegrationStatus


class TUportalAdapter(ABC):
    name: str
    is_mock: bool

    @abstractmethod
    def get_student_profile(self, student_id: str) -> dict: ...
    @abstractmethod
    def get_degree_audit(self, student_id: str) -> dict: ...
    @abstractmethod
    def get_academic_history(self, student_id: str) -> list[dict]: ...
    @abstractmethod
    def get_available_sections(self, term_id: str) -> list[dict]: ...
    @abstractmethod
    def get_registration_restrictions(self, student_id: str, term_id: str) -> list[dict]: ...
    @abstractmethod
    def create_draft_schedule(self, student_id: str, term_id: str, plan_id: str, option_id: str, crns: list[str]) -> dict: ...
    @abstractmethod
    def validate_draft_schedule(self, draft_id: str) -> dict: ...
    @abstractmethod
    def get_draft_schedule(self, draft_id: str) -> dict | None: ...


class MockTUportalAdapter(TUportalAdapter):
    name = "mock_tuportal"
    is_mock = True

    def __init__(self, db: Session):
        self.db = db

    def _record(self, op: str, status: str, payload: dict, plan_id=None, option_id=None) -> IntegrationStatus:
        row = IntegrationStatus(adapter=self.name, operation=op, status=status, payload=payload,
                                plan_id=plan_id, option_id=option_id, is_mock=True)
        self.db.add(row)
        self.db.commit()
        return row

    def get_student_profile(self, student_id):
        return {"mock": True, "note": "Mock adapter: student profile comes from the planner's own records."}

    def get_degree_audit(self, student_id):
        return {"mock": True, "note": "Mock adapter: no Degree Audit connection."}

    def get_academic_history(self, student_id):
        return []

    def get_available_sections(self, term_id):
        return []

    def get_registration_restrictions(self, student_id, term_id):
        return [{"mock": True, "restriction": "None simulated. Real holds/restrictions must come from Banner."}]

    def create_draft_schedule(self, student_id, term_id, plan_id, option_id, crns):
        draft_id = f"MOCK-DRAFT-{uuid.uuid4().hex[:8].upper()}"
        payload = {"draft_id": draft_id, "student_id": student_id, "term_id": term_id, "crns": crns,
                   "environment": "MOCK planning environment (not TUportal)", "registered": False}
        self._record("create_draft_schedule", "saved", payload, plan_id, option_id)
        return payload

    def validate_draft_schedule(self, draft_id):
        draft = self.get_draft_schedule(draft_id)
        if not draft:
            return {"draft_id": draft_id, "valid": False, "messages": ["Draft not found"]}
        result = {"draft_id": draft_id, "valid": True, "mock": True,
                  "messages": ["Mock validation only: holds, time tickets, seat availability and restrictions were NOT checked against Banner."]}
        self._record("validate_draft_schedule", "mock_validated", result)
        return result

    def get_draft_schedule(self, draft_id):
        for row in self.db.query(IntegrationStatus).filter_by(adapter=self.name, operation="create_draft_schedule").all():
            if row.payload.get("draft_id") == draft_id:
                return row.payload
        return None
