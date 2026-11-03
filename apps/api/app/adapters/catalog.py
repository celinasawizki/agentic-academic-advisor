"""Academic requirements catalog. Requirements are ingested (with source URL,
retrieval timestamp and catalog year) rather than generated."""

import json
from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain import RequirementData
from app.models import AcademicProgram


class RequirementsCatalogAdapter(ABC):
    @abstractmethod
    def programs(self) -> dict[str, dict]: ...

    @abstractmethod
    def requirements(self, program_ids: list[str]) -> list[RequirementData]: ...

    @abstractmethod
    def double_count_allowed(self) -> set[frozenset[str]]: ...


class DbCatalogAdapter(RequirementsCatalogAdapter):
    def __init__(self, db: Session):
        self.db = db

    def programs(self) -> dict[str, dict]:
        out = {}
        for p in self.db.query(AcademicProgram).all():
            out[p.id] = {"id": p.id, "name": p.name, "type": p.type, "college": p.college, "catalog_year": p.catalog_year,
                         "supported": p.supported, "source_url": p.source.url if p.source else None,
                         "retrieved_at": p.source.retrieved_at.isoformat() if p.source else None,
                         "verification_status": p.source.verification_status if p.source else "unknown"}
        return out

    def requirements(self, program_ids: list[str]) -> list[RequirementData]:
        out = []
        for p in self.db.query(AcademicProgram).filter(AcademicProgram.id.in_(program_ids)).all():
            for r in p.requirements:
                out.append(RequirementData(id=r.id, program_id=p.id, program_name=p.name, program_type=p.type, name=r.name,
                                           rule=r.rule, choose_count=r.choose_count, courses=r.courses, category=r.category,
                                           catalog_year=r.catalog_year, verification_status=r.verification_status,
                                           source_url=p.source.url if p.source else None))
        return out

    def double_count_allowed(self) -> set[frozenset[str]]:
        data = json.loads((settings.data_dir / "programs.json").read_text())
        return {frozenset(r["programs"]) for r in data.get("double_count_rules", []) if r["allowed"]}


class BulletinIngestionAdapter:
    """Future: fetch official bulletin pages, extract requirement tables into
    ProgramRequirement rows, and queue anything ambiguous for human review
    (verification_status='needs_review'). Not implemented in the MVP."""
