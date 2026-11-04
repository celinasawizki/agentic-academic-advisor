"""Graduation-plan ingestion. Temple advisors hand students an E-Graduation Plan
PDF: a grid of semester blocks ("FALL 2026", "SPRING 2027", ...), each with a
Course column and a Credits column. Text extraction alone interleaves the
columns, so this parser works from text positions: a semester heading owns the
course lines below it that start in its column, until the next heading row.

Parsing is local and rule-based; nothing is sent to an LLM. Lines without a
course code (e.g. "GenEd Science/Tech course (GS2)") are kept as open slots and
never resolved to a guessed course. The student reviews every row."""

import io
import re
from dataclasses import dataclass

from pypdf import PdfReader

TERM_HEAD_RE = re.compile(r"^\s*(FALL|SPRING|SUMMER|WINTER)\s+(\d{4})\b", re.I)
PANEL_HEAD_RE = re.compile(r"^\s*(FALL|SPRING|SUMMER|WINTER)\b", re.I)  # blank template blocks ("FALL 20") and side panels
COURSE_AT_START_RE = re.compile(r"^([A-Z]{2,5})\s?(\d{4})(?![\w-])")  # not "PSY 2000-level"
NUMBER_RE = re.compile(r"^\s*(\d{1,2}(?:\.\d)?)\s*$")
TRAILING_NUMBER_RE = re.compile(r"^\s*([A-Z]{2,5})\b.*?-\s*(\d{4})\s*$")
SKIP_RE = re.compile(r"^\s*(TOTAL|Course|Credits)\b", re.I)
WINTER_RE = re.compile(r"\bwinter\b", re.I)
UNSURE_RE = re.compile(r"\?|\bcheck with\b|\bis this needed\b", re.I)
SAME_LINE = 2.5   # points; fragments within this vertical distance are one row
COLUMN_TOL = 25   # points; a course line belongs to the nearest heading at or right of it


@dataclass
class Frag:
    x: float
    y: float
    text: str


def _fragments(page) -> list[Frag]:
    out: list[Frag] = []

    def visit(text, cm, tm, _font, _size):
        if text and text.strip():
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            out.append(Frag(x, y, text.replace("\n", " ")))

    page.extract_text(visitor_text=visit)
    return out


def term_label(season: str, year: str) -> str:
    return f"{season.capitalize()} {year}"


def _item(text: str, credits: float | None, known: set[str]) -> dict:
    text = " ".join(text.split())
    m = COURSE_AT_START_RE.match(text)
    course = f"{m.group(1)} {m.group(2)}" if m else None
    rest = text[m.end():].strip() if m else text
    notes = [n.strip() for n in re.findall(r"\(([^)]*)\)", rest)]
    suffix = rest.split(" - ", 1)[1].strip() if " - " in rest else ""
    flags = []
    if WINTER_RE.search(text):
        flags.append("winter_session")
    if UNSURE_RE.search(text):
        flags.append("needs_confirmation")
    suggested = None
    if course is None:
        t = TRAILING_NUMBER_RE.match(text)  # "PSY 2000-level BCS course (major) - 2104" → a hint, not a decision
        if t:
            suggested = f"{t.group(1)} {t.group(2)}"
    return {
        "course": course,
        "label": text if course is None else (rest or course),
        "credits": credits,
        "notes": notes + ([suffix] if suffix else []),
        "flags": flags,
        "suggested_course": suggested,
        "in_catalog": course in known if course else None,
        # Winter-session courses written into a spring column are not part of that semester's schedule.
        "include": bool(course) and "winter_session" not in flags,
        "raw_line": text[:160],
    }


def parse_grad_plan_pages(pages: list[list[Frag]], known: set[str]) -> dict:
    terms: dict[str, dict] = {}
    notes: list[str] = []
    header_text = ""
    for frags in pages:
        # A block heading has its "Course" column label directly beneath it; a line such as
        # "Summer 2026?" inside a side panel does not.
        labels = [f for f in frags if f.text.strip() == "Course"]
        heads = [f for f in frags if PANEL_HEAD_RE.match(f.text)
                 and any(0 < f.y - c.y <= 16 for c in labels)]
        rows: dict[float, list[Frag]] = {}
        for h in heads:
            key = next((k for k in rows if abs(k - h.y) <= SAME_LINE), h.y)
            rows.setdefault(key, []).append(h)
        head_rows = sorted(rows.items(), key=lambda kv: -kv[0])  # top of page first
        if not header_text:
            header_text = " ".join(f.text.strip() for f in sorted(frags, key=lambda f: (-f.y, f.x))
                                   if "Graduation Plan" in f.text or f.text.strip().startswith(("Major:", "Minor:", "Other:")))
        for i, (row_y, row_heads) in enumerate(head_rows):
            floor = head_rows[i + 1][0] if i + 1 < len(head_rows) else -1e9
            block = [f for f in frags if floor + SAME_LINE < f.y < row_y - SAME_LINE and not SKIP_RE.match(f.text)
                     and not PANEL_HEAD_RE.match(f.text)]
            row_heads = sorted(row_heads, key=lambda h: h.x)
            # Course text starts left of its (centered) heading; credits sit further right on the same line.
            texts = [f for f in block if not NUMBER_RE.match(f.text)]
            numbers = [f for f in block if NUMBER_RE.match(f.text)]

            def owner(x: float):
                right = [h for h in row_heads if h.x >= x - COLUMN_TOL]
                return right[0] if right else None

            line_items: list[tuple[Frag, Frag]] = []  # (heading, text fragment)
            for t in texts:
                h = owner(t.x)
                if h is None:
                    continue
                if not TERM_HEAD_RE.match(h.text):
                    continue  # blank template block or side panel (Summer Courses, Additional Resources)
                if h is not row_heads[-1] and t.x > row_heads[row_heads.index(h) + 1].x - COLUMN_TOL:
                    continue
                line_items.append((h, t))
            # Also skip the right-hand side panel: lines that start right of the last term column's credits.
            col_starts = {}
            for h, t in line_items:
                col_starts.setdefault(id(h), []).append(t.x)
            for h, t in line_items:
                start = min(col_starts[id(h)])
                if t.x - start > COLUMN_TOL:
                    continue
                if not COURSE_AT_START_RE.match(t.text.strip()) and not re.search(r"(?i)course|elective|gen ?ed|\([A-Z]{1,3}\d?\)", t.text):
                    continue
                same_row = [n for n in numbers if abs(n.y - t.y) <= SAME_LINE and n.x > t.x]
                nxt = [tt.x for tt in texts if abs(tt.y - t.y) <= SAME_LINE and tt.x > t.x]  # stop at the next column
                limit = min(nxt) if nxt else 1e9
                cred = next((float(NUMBER_RE.match(n.text).group(1)) for n in sorted(same_row, key=lambda n: n.x) if n.x < limit), None)
                m = TERM_HEAD_RE.match(h.text)
                label = term_label(m.group(1), m.group(2))
                term = terms.setdefault(label, {"term": label, "heading": " ".join(h.text.split()), "items": []})
                term["items"].append(_item(t.text, cred, known))
    out_terms = list(terms.values())
    for t in out_terms:
        t["planned_credits"] = sum(i["credits"] or 0 for i in t["items"] if i["include"])
    if not out_terms:
        notes.append("No semester headings (e.g. 'SPRING 2027') were found. Is this an E-Graduation Plan PDF?")
    else:
        open_slots = sum(1 for t in out_terms for i in t["items"] if not i["course"])
        if open_slots:
            notes.append(f"{open_slots} line(s) name a requirement slot instead of a course; they are not scheduled until you pick a course.")
    notes.append("Extracted with a local rule-based parser. Review every semester before it is used.")
    # The heading carries the student's name and TUID; keep only the program line.
    programs = re.sub(r"^.*?Graduation Plan:[^)]*\)\s*", "", " ".join(header_text.split()))
    return {"source": programs[:200] or None, "terms": out_terms, "notes": notes}


def parse_grad_plan(pdf_bytes: bytes, known_courses: set[str]) -> dict:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return parse_grad_plan_pages([_fragments(p) for p in reader.pages], known_courses)


def term_courses(grad_plan: list[dict], term_name: str) -> list[dict]:
    """The included, course-coded items the plan lists for one semester."""
    for t in grad_plan or []:
        if t.get("term", "").lower() == term_name.lower():
            return [i for i in t.get("items", []) if i.get("course") and i.get("include", True)]
    return []
