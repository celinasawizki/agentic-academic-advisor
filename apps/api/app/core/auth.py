"""Authentication and record-level authorization.

Three kinds of records exist and are kept separate:
  1. Fictional demo students (Student.is_demo) — shared, read/plan by anyone, never deleted.
  2. Real student records — accessible only to the student who owns them.
  3. Advisor access — the demo advisor role sees fictional students only. Real advisor
     access requires an institutional identity provider (Temple SSO) plus an
     advisor-to-student assignment check, which this prototype does not have.

The AuthProvider seam is where Temple SSO (OIDC/SAML) plugs in later; until then the
prototype issues an opaque per-student bearer token at record creation (only its
SHA-256 hash is stored). Denials return 404 so record IDs cannot be probed."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Literal, Protocol

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import PlanRun, Student

Action = Literal["read", "plan", "modify", "delete", "export", "advise"]


@dataclass(frozen=True)
class Principal:
    kind: Literal["anonymous", "student", "demo_advisor"]
    student_id: str | None = None
    provider: str = "prototype_token"


class AuthProvider(Protocol):
    def authenticate(self, request: Request, db: Session) -> Principal: ...


def new_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class PrototypeTokenProvider:
    def authenticate(self, request: Request, db: Session) -> Principal:
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            token = header[7:].strip()
            if token:
                digest = hash_token(token)
                student = db.query(Student).filter(Student.access_token_hash == digest).first()
                if student and student.access_token_hash and hmac.compare_digest(student.access_token_hash, digest):
                    return Principal(kind="student", student_id=student.id)
        if request.headers.get("x-demo-role") == "advisor":
            return Principal(kind="demo_advisor", provider="demo_role_header")
        return Principal(kind="anonymous")


class TempleSSOProvider:
    """Placeholder for Temple single sign-on. Needs Temple IAM approval, client registration
    and an advisor-assignment source before it can authorize any real record."""

    def authenticate(self, request: Request, db: Session) -> Principal:
        raise HTTPException(501, "Temple SSO is not configured for this prototype.")


provider: AuthProvider = PrototypeTokenProvider()


def get_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    return provider.authenticate(request, db)


def can_access(principal: Principal, student: Student, action: Action) -> bool:
    if student.is_demo:
        return action != "delete"
    if principal.kind == "student" and principal.student_id == student.id:
        return action != "advise"
    return False


def authorize_student(db: Session, principal: Principal, student_id: str, action: Action) -> Student:
    student = db.get(Student, student_id)
    if student is None or not can_access(principal, student, action):
        raise HTTPException(404, "Student not found")
    return student


def authorize_plan(db: Session, principal: Principal, plan_id: str, action: Action) -> PlanRun:
    plan = db.get(PlanRun, plan_id)
    student = db.get(Student, plan.student_id) if plan else None
    if plan is None or student is None or not can_access(principal, student, action):
        raise HTTPException(404, "Plan not found")
    return plan
