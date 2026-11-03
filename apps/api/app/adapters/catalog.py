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
                         "supported": p.supported, "total_credit_hours": p.total_credit_hours,
                         "layers": p.layers or [], "min_grade": p.min_grade,
                         "source_url": p.source.url if p.source else None,
                         "retrieved_at": p.source.retrieved_at.isoformat() if p.source else None,
                         "verification_status": p.source.verification_status if p.source else "unknown"}
        return out

    def requirements(self, program_ids: list[str]) -> list[RequirementData]:
        out = []
        found = {p.id: p for p in self.db.query(AcademicProgram).filter(AcademicProgram.id.in_(program_ids)).all()}
        for pid in program_ids:
            if (p := found.get(pid)) is None:
                continue
            for r in p.requirements:
                out.append(RequirementData(id=r.id, program_id=p.id, program_name=p.name, program_type=p.type, group=r.group,
                                           name=r.name, kind=r.kind, needed=r.needed, options=r.options or [],
                                           patterns=r.patterns or [], notes=r.notes or [], catalog_year=r.catalog_year,
                                           verification_status=r.verification_status, source_url=p.source.url if p.source else None,
                                           min_grade=(p.min_grade or {}).get("grade"), evidence=r.evidence))
        return out

    def verified_rules(self) -> dict[str, dict]:
        f = settings.data_dir / "verifications.json"
        data = json.loads(f.read_text()) if f.exists() else {}
        return {v["rule_id"]: v for v in data.get("verified_rules", []) if v.get("rule_id") and v.get("verified_by") and v.get("evidence")}

    def double_count_allowed(self) -> set[frozenset[str]]:
        f = settings.data_dir / "programs.json"
        data = json.loads(f.read_text()) if f.exists() else {}
        return {frozenset(r["programs"]) for r in data.get("double_count_rules", []) if r["allowed"]}


# Bulletin ingestion lives in app/ingest/bulletin.py (parsers) and
# scripts/ingest_bulletin.py (polite crawler that writes data/temple/*.json).
