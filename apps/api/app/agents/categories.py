"""Course roles in a plan. A course that matches a student's interests is never presented as
satisfying a degree requirement unless a parsed requirement rule actually lists or matches it."""

REQUIRED = "REQUIRED"
DEGREE_ELECTIVE = "DEGREE_ELECTIVE"
INTEREST_ELECTIVE = "INTEREST_ELECTIVE"
OPTIONAL_ENRICHMENT = "OPTIONAL_ENRICHMENT"

LABELS = {
    REQUIRED: "Required course",
    DEGREE_ELECTIVE: "Degree elective",
    INTEREST_ELECTIVE: "Interest-based elective",
    OPTIONAL_ENRICHMENT: "Optional enrichment",
}


def all_eligible(state: dict) -> list[dict]:
    """Requirement-linked eligible sections plus interest-based elective sections."""
    out = list(state.get("course_discovery", {}).get("eligible_sections", []))
    for el in state.get("interest_matching", {}).get("interest_electives", []):
        out.extend(el["sections"])
    return out


def classify(course: str, requirement_ids: list[str], state: dict) -> str:
    if not requirement_ids or set(requirement_ids) <= {"FREE_ELECTIVE"}:
        return INTEREST_ELECTIVE
    reqs = {r["id"]: r for r in state.get("degree_requirements", {}).get("remaining", [])}
    for rid in requirement_ids:
        r = reqs.get(rid)
        if r and r["kind"] == "count" and len(r["options"]) == 1 and not r["patterns"] and course in r["options"][0]:
            return REQUIRED
    return DEGREE_ELECTIVE
