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
