"""Normalization for class-search section data."""


def modality(method: str | None, desc: str | None) -> str:
    """Map Banner instructional methods to in_person / online / hybrid / unknown.
    Mixed formats are hybrid; arranged non-classroom work is unknown (never assumed in-person)."""
    d = f"{method or ''} {desc or ''}".lower()
    if "non-classroom" in d or not d.strip():
        return "unknown"
    if "mix" in d or "hybrid" in d or "blend" in d:
        return "hybrid"
    if "online" in d or "distance" in d or "remote" in d:
        return "online"
    if any(k in d for k in ("classroom", "in-person", "in person", "studio", "laboratory", "lab", "clinical")):
        return "in_person"
    return "unknown"


SECONDARY_TYPES = ("recitation", "laboratory", "lab", "discussion")


def component_of(schedule_type: str | None, course_types: set[str]) -> str:
    """'primary' for the main meeting (lecture, lecture+lab, ...); otherwise the separate
    component type (Lab, Recitation, ...). Temple's class search publishes no section
    linkage, so this pairing is inferred from schedule types and is never 'verified'."""
    t = (schedule_type or "").strip()
    if t.lower() in SECONDARY_TYPES and any(x.lower() not in SECONDARY_TYPES for x in course_types):
        return t
    return "primary"


def assign_components(sections: list) -> list:
    """Return copies of SectionData with `component` set, grouped per course."""
    types: dict[str, set[str]] = {}
    for s in sections:
        types.setdefault(s.course, set()).add(s.schedule_type or "")
    return [s.model_copy(update={"component": component_of(s.schedule_type, types[s.course])}) for s in sections]


def components_by_course(sections: list) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for s in sections:
        out.setdefault(s.course, set()).add(s.component)
    return out
