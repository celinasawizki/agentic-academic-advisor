from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.domain import CourseData, RequirementData, SectionData, StudentProfile
from app.models import AgentExecution


@dataclass
class Catalog:
    term_id: str
    term_name: str
    courses: dict[str, CourseData]
    sections: list[SectionData]
    requirements: list[RequirementData]
    programs: dict[str, dict]
    double_count_allowed: set[frozenset[str]]
    verified_rules: dict[str, dict] = field(default_factory=dict)


@dataclass
class PlanContext:
    db: Session
    plan_id: str
    student: StudentProfile
    catalog: Catalog
    state: dict[str, Any]
    iteration: int = 1
    _exec: AgentExecution | None = field(default=None, repr=False)

    def log(self, message: str, **data: Any) -> None:
        if self._exec is not None:
            self._exec.log = [*self._exec.log, {"t": datetime.now(timezone.utc).isoformat(), "message": message, "data": data}]

    def cite(self, kind: str, description: str, url: str | None = None, retrieved_at: str | None = None,
             verification_status: str = "demo_unverified") -> None:
        if self._exec is not None:
            src = {"kind": kind, "description": description, "url": url, "retrieved_at": retrieved_at,
                   "verification_status": verification_status}
            if src not in self._exec.sources:
                self._exec.sources = [*self._exec.sources, src]

    def set_mode(self, mode: str) -> None:
        if self._exec is not None:
            self._exec.mode = mode


class Agent:
    key: str = ""
    title: str = ""
    responsibility: str = ""

    def run(self, ctx: PlanContext) -> dict:  # pragma: no cover - interface
        raise NotImplementedError

    def summarize(self, output: dict) -> str:
        return ""
