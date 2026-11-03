"""Degree audit ingestion. Temple's Degree Audit (DARS / uAchieve, see
sites.temple.edu/degreeaudit) is behind university authentication and has no
public API, so the MVP parses a student-uploaded PDF locally. Uploaded content
is never sent to an external LLM by default."""

import io
import re

from pypdf import PdfReader

COURSE_RE = re.compile(r"\b([A-Z]{2,5})\s?(\d{4})\b")
TERM_RE = re.compile(r"\b(FA|SP|SU|Fall|Spring|Summer)\s?'?(\d{2,4})\b", re.I)
GRADE_RE = re.compile(r"\b(A-|A|B\+|B-|B|C\+|C-|C|D\+|D|F|P|TR|IP|CR)\b")


def extract_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def parse_audit_text(text: str, known_courses: set[str]) -> dict:
    entries, seen = [], set()
    for line in text.splitlines():
        for subj, num in COURSE_RE.findall(line):
            code = f"{subj} {num}"
            if code in seen:
                continue
            seen.add(code)
            grade_m = GRADE_RE.search(line[line.find(num) + 4:])
            grade = grade_m.group(1) if grade_m else None
            upper = line.upper()
            if "IN PROGRESS" in upper or grade == "IP" or " IP " in f" {upper} ":
                status, grade = "in_progress", None
            elif grade == "TR" or "TRANSFER" in upper:
                status = "transfer"
            elif "PLANNED" in upper or "REGISTERED" in upper:
                status = "planned"
            elif grade:
                status = "completed"
            else:
                status = "unverified"
            confidence = 0.5
            if grade or status == "in_progress":
                confidence += 0.3
            if code in known_courses:
                confidence += 0.15
            term_m = TERM_RE.search(line)
            entries.append({"course": code, "status": status, "grade": grade,
                            "term": term_m.group(0) if term_m else None, "source": "degree_audit_pdf",
                            "confidence": round(min(confidence, 0.95), 2), "raw_line": line.strip()[:160],
                            "in_catalog": code in known_courses})
    return {"entries": entries, "line_count": len(text.splitlines()),
            "notes": ["Extracted with a local rule-based parser. Review every row before it is used."]}


class TempleDegreeAuditAdapter:
    """Future authorized integration (e.g. via a TUportal test environment)."""

    def get_degree_audit(self, student_id: str):
        raise NotImplementedError("No authorized Degree Audit API is available; upload a PDF instead.")
