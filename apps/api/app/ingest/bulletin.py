"""Parsers for Temple's CourseLeaf-based Academic Bulletin (bulletin.temple.edu).

Requirements are parsed conservatively: anything that is not an explicit course
row, an "or" alternative, or a "Select N ... of the following" group is kept as
text and marked needs_review rather than guessed."""

import html as htmllib
import re
from dataclasses import dataclass, field

CODE = r"[A-Z]{2,5}\s\d{4}"
CODE_RE = re.compile(rf"\b({CODE})\b")
NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
             "eleven": 11, "twelve": 12, "a": 1, "an": 1}
DEGREE_SUFFIX = re.compile(r"-(ba|bs|bba|bfa|bm|bmus|bsn|bse|bsw|bsed|bsba|barch|bla|bsee|bsme|bsce|bsie|bsbe|bsae|bsm|bsph|bsr|bps|bat|mus)$")


def clean(fragment: str) -> str:
    text = re.sub(r"<sup[^>]*>.*?</sup>", "", fragment, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = htmllib.unescape(text).replace("\xa0", " ").replace("​", "")
    return re.sub(r"\s+", " ", text).strip()


def norm_code(code: str) -> str:
    return re.sub(r"\s+", " ", code.strip())


def program_type(slug: str) -> str | None:
    if slug.endswith("-minor"):
        return "minor"
    if slug.endswith("-certificate") or slug.endswith("-certificate-of-specialization"):
        return "certificate"
    if DEGREE_SUFFIX.search(slug):
        return "major"
    return None


@dataclass
class Req:
    group: str
    name: str
    kind: str  # count | credits | manual | note
    needed: float
    options: list[list[str]] = field(default_factory=list)
    patterns: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    needs_review: bool = False

    def to_dict(self) -> dict:
        return {"group": self.group, "name": self.name, "kind": self.kind, "needed": self.needed, "options": self.options,
                "patterns": self.patterns, "notes": self.notes,
                "verification_status": "needs_review" if self.needs_review else "parsed"}


SELECT_RE = re.compile(
    r"^(?:select|choose|complete|take)\s+(?:at least\s+|a minimum of\s+|any\s+)?(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|a|an)"
    r"(?:\s*(?:-|to)\s*\d+)?\s*(courses?|credits?|credit hours?|s\.h\.|electives?|of)?\b", re.I)
RANGE_RE = re.compile(rf"\b([A-Z]{{2,5}})\s(\d{{4}})\s?(?:-|to|through)\s?(\d{{4}})\b")
LEVEL_RE = re.compile(r"\b([A-Z]{2,5})\b[^.]{0,40}?\b([1-4])000[- ]level\b", re.I)


TRACK_RE = re.compile(r"(select|choose|complete) one (?:of the following )?[\w\s]{0,30}?(sequences?|tracks?)\b|options listed below", re.I)
LEGEND_RE = re.compile(r"^\((F|S|SE|SO|FE|FO|O|SU|Y)\)\s*(-|=)|^note:|symbol after the course title", re.I)
NOTE_PHRASES = ("general education courses", "free elective", "genEd ".lower(), "(all students must be proficient", "is strongly recommended")
COMBO_RE = re.compile(r"(?:any combination|combination of)[^.]*?total of (\d+(?:\.\d+)?) (?:credit|s\.h)", re.I)
XLIST_RE = re.compile(r"^(?:or\s+)?((?:[A-Z]{2,5}/)+[A-Z]{2,5})\s(\d{4})\b")


def _row_codes(code_text: str, linked: bool) -> list[list[str]]:
    """Course codes for a requirement row. Cross-listed 'IB/MKTG 3501' expands to its subjects;
    rows must start with a code so text like 'PSY 3000-3620' is not mistaken for a course."""
    x = XLIST_RE.match(code_text)
    if x:
        return [[f"{subj} {x.group(2)}"] for subj in x.group(1).split("/")]
    if not re.match(rf"^(or\s+)?{CODE}(\s*&\s*{CODE})*(\s|$)", code_text):
        return []
    if not linked and RANGE_RE.match(code_text.removeprefix("or ").strip()):
        return []
    head = re.match(rf"^(?:or\s+)?({CODE}(?:\s*&\s*{CODE})*)", code_text).group(1)
    return [[norm_code(c) for c in CODE_RE.findall(head)]]


def _number(token: str) -> int:
    return int(token) if token.isdigit() else NUM_WORDS[token.lower()]


def _hours(text: str) -> float | None:
    m = re.match(r"^(\d+(?:\.\d+)?)", text.strip())
    return float(m.group(1)) if m else None


def parse_patterns(text: str) -> list[dict]:
    pats = []
    for subj, lo, hi in RANGE_RE.findall(text):
        pats.append({"subject": subj, "min": int(lo), "max": int(hi)})
    if not pats:
        for subj, lvl in LEVEL_RE.findall(text):
            if subj.upper() == subj and len(subj) >= 2:
                pats.append({"subject": subj, "min": int(lvl) * 1000, "max": int(lvl) * 1000 + 999})
    return pats


def parse_requirement_tables(container_html: str) -> list[Req]:
    """Walk headings and sc_courselist tables in document order."""
    reqs: list[Req] = []
    heading = "Requirements"
    pos = 0
    seen_total = False
    token_re = re.compile(r"<h[2-5][^>]*>(.*?)</h[2-5]>|<(?:p|li)[^>]*>\s*<strong>(.*?)</strong>|<table class=\"sc_courselist[^\"]*\"[^>]*>(.*?)</table>", re.S)
    last_table_end = 0
    for m in token_re.finditer(container_html, pos):
        if m.group(3) is not None:
            between = clean(container_html[last_table_end:m.start()])
            last_table_end = m.end()
        if m.group(3) is None:
            text = re.sub(r"\s*\d$", "", clean(m.group(1) or m.group(2) or ""))
            heading = text.rstrip(":") or heading
            continue
        parsed = _parse_table(m.group(3), heading)
        has_total = "listsum" in m.group(3)
        if TRACK_RE.search(between[-350:]) or TRACK_RE.search(heading):
            for r in parsed:
                r.kind, r.needed, r.needs_review = "note", 0, True
                r.notes.append("Part of a set of alternative tracks/sequences (choose one); listed for reference, not added as a separate requirement.")
            seen_total = seen_total or has_total
            reqs.extend(parsed)
            continue
        binding = bool(re.search(r"\b(select|choose|required|requirements?|concentration|take)\b", heading, re.I)) \
            and not re.search(r"summary|select up to|recommended|suggested", heading, re.I)
        if seen_total and not has_total and not binding:
            for r in parsed:
                r.kind, r.needed, r.needs_review = "note", 0, True
                r.notes.append(f"Listed after the program's credit total under '{heading}'; treated as supplementary information, not a requirement.")
        seen_total = seen_total or has_total
        if re.search(r"\balternat", heading, re.I):
            for r in parsed:
                r.kind, r.needed, r.needs_review = "note", 0, True
                r.notes.append(f"Listed under '{heading}': an alternative path, not an additional requirement. Confirm which path applies.")
        reqs.extend(parsed)
    return [r for r in reqs if r.kind != "note" or r.notes]


def _parse_table(table_html: str, heading: str) -> list[Req]:
    out: list[Req] = []
    area = heading
    group: Req | None = None
    last_target: list[str] | None = None  # option list that an "or" row extends
    last_req: Req | None = None
    for cls, body in re.findall(r"<tr class=\"([^\"]*)\"[^>]*>(.*?)</tr>", table_html, re.S):
        if "hidden" in cls or "listsum" in cls:
            continue
        cells = re.findall(r"<td([^>]*)>(.*?)</td>", body, re.S)
        if not cells:
            continue
        code_html = next((c for a, c in cells if "codecol" in a), cells[0][1])
        hours_txt = clean(next((c for a, c in cells if "hourscol" in a), ""))
        row_text = clean(" ".join(c for _, c in cells))
        if "areaheader" in cls:
            head = re.sub(r"\s\d$", "", clean(cells[0][1]))
            sel = SELECT_RE.match(head)
            if sel and ("following" in head.lower() or head.rstrip().endswith(":")):
                unit = (sel.group(2) or "").lower()
                group = Req(group=area, name=head.rstrip(":"), kind="credits" if unit.startswith(("credit", "s.h")) else "count",
                            needed=_number(sel.group(1)))
                out.append(group)
                last_req = group
                continue
            area = head or area
            group = None
            continue
        code_text = clean(code_html)
        codes = _row_codes(code_text, "bubblelink" in code_html)
        if "orclass" in cls and codes:
            if last_req is not None and last_req.options:
                last_req.options.extend(codes)
            continue
        if codes:
            title = clean(cells[1][1]) if len(cells) > 1 else ""
            if group is not None:
                group.options.extend(codes)
                last_req = group
            else:
                hours = _hours(hours_txt)
                r = Req(group=area, name=f"{' or '.join(' & '.join(o) for o in codes)} {title}".strip(), kind="count", needed=1, options=list(codes))
                if hours:
                    r.notes.append(f"{hours_txt} credit hours")
                out.append(r)
                last_req = r
            continue
        text = re.sub(r"\s\d$", "", row_text)
        low = text.lower()
        if LEGEND_RE.search(text) or any(k in low for k in NOTE_PHRASES):
            out.append(Req(group=area, name=text, kind="note", needed=0, notes=[text]))
            group = None
            continue
        combo = COMBO_RE.search(text)
        if combo:
            group = Req(group=area, name=text.rstrip(":"), kind="credits", needed=float(combo.group(1)))
            out.append(group)
            last_req = group
            continue
        if re.match(r"^select (one or more )?from the following", low):
            hours = _hours(hours_txt)
            group = Req(group=area, name=text.rstrip(":"), kind="credits" if hours else "count", needed=hours or 1, needs_review=True,
                        notes=["Number of courses not stated; credit hours from the bulletin table were used."])
            out.append(group)
            last_req = group
            continue
        sel = SELECT_RE.match(text)
        if sel and ("following" in low or "from" in low or text.rstrip().endswith(":")):
            n = _number(sel.group(1))
            unit = (sel.group(2) or "").lower()
            kind = "credits" if unit.startswith(("credit", "s.h")) else "count"
            group = Req(group=area, name=re.sub(r":?\s*[\d.]+(?:-[\d.]+)?$", "", text).rstrip(":"), kind=kind, needed=n)
            pats = parse_patterns(text)
            if pats:
                group.patterns = pats
            out.append(group)
            last_req = group
            continue
        if "substitut" in text.lower():
            group = Req(group=area, name=text, kind="note", needed=0, notes=[text])
            out.append(group)
            last_req = group
            continue
        hours = _hours(hours_txt)
        pats = parse_patterns(text)
        if pats:
            needed = round(hours / 3) if hours else 1
            r = Req(group=area, name=text, kind="count", needed=max(1, needed), patterns=pats, needs_review=True,
                    notes=[f"Parsed course-range rule from text: '{text}'. Verify with an advisor."])
        else:
            r = Req(group=area, name=text, kind="manual", needed=hours or 0, needs_review=True,
                    notes=[f"Rule could not be parsed automatically: '{text}'"])
        group = None
        out.append(r)
        last_req = r
    return out


def section_html(page: str, container_id: str) -> str:
    start = page.find(f'id="{container_id}"')
    if start < 0:
        return ""
    nxt = re.search(r'<div id="[a-z]+textcontainer"', page[start + 20:])
    return page[start: start + 20 + nxt.start()] if nxt else page[start:]


def parse_program_page(page: str, url: str) -> dict:
    title_m = re.search(r'<h1 class="page-title">(.*?)</h1>', page, re.S)
    title = clean(title_m.group(1)) if title_m else url.rstrip("/").split("/")[-1]
    req_html = section_html(page, "requirementstextcontainer") or section_html(page, "textcontainer")
    year_m = re.search(r"matriculated in academic year (\d{4}-\d{4})", clean(req_html))
    total_m = re.findall(r"Total Credit Hours\s*</td>\s*<td[^>]*>([^<]+)<", req_html)
    reqs = parse_requirement_tables(req_html)
    return {"title": title, "catalog_year": year_m.group(1) if year_m else None, "requirements": [r.to_dict() for r in reqs],
            "total_credit_hours": [clean(t) for t in total_m]}


# ---- courses -------------------------------------------------------------

TITLE_RE = re.compile(rf"^({CODE})\.\s+(.*?)\.\s+(\d+(?:\.\d+)?)(?:\s*(?:to|or|-)\s*(\d+(?:\.\d+)?))?\s+Credit Hours?\.?$")


def parse_course_blocks(page: str) -> list[dict]:
    out = []
    for block in re.split(r'<div class="courseblock">', page)[1:]:
        t = re.search(r'<p class="courseblocktitle">(.*?)</p>', block, re.S)
        if not t:
            continue
        m = TITLE_RE.match(clean(t.group(1)))
        if not m:
            continue
        code, title, lo, hi = norm_code(m.group(1)), m.group(2), float(m.group(3)), m.group(4)
        if lo == 0 and hi:
            lo = float(hi)
        if int(code.split()[1]) >= 5000:
            continue
        desc_m = re.search(r'<div class="courseblockheaddiv">(.*?)</div>', block, re.S)
        attrs_m = re.search(r"Course Attributes:</strong>([^<]*)", block)
        pre_m = re.search(r"Pre-requisites:</strong>(.*?)</p>", block, re.S)
        prereq_text = clean(pre_m.group(1)) if pre_m else ""
        groups, notes = parse_prereqs(prereq_text) if prereq_text else ([], [])
        out.append({
            "code": code, "title": title, "credits": lo, "credits_max": float(hi) if hi else lo,
            "description": clean(desc_m.group(1)) if desc_m else "",
            "attributes": [a.strip() for a in attrs_m.group(1).split(",") if a.strip()] if attrs_m else [],
            "prereq_text": prereq_text, "prereqs": groups, "prereq_notes": notes,
        })
    return out


OTHER = "@OTHER"  # a non-course alternative (placement test, standing, program)
_TOKEN = re.compile(rf"(?:\s+)|({CODE})|(\()|(\))|(,)|\b((?i:and))\b|\b((?i:or))\b|([^(),]+?)(?=\(|\)|,|\b(?i:and)\b|\b(?i:or)\b|$)")


def _tokens(text: str) -> list[tuple[str, str]]:
    text = re.sub(r"(?i)\((?:[^()]*?(?:higher|concurrent|except where noted|or better)[^()]*)\)", " ", text)
    text = re.sub(r"(?i)minimum grade of [A-F][+-]?\s*(?:\([^)]*\))?\s*in", " ", text)
    text = re.sub(r"(?i)(may not be taken concurrently|can be taken concurrently|undergraduate level)", " ", text)
    toks = []
    for m in _TOKEN.finditer(text):
        if not any(m.groups()):
            continue
        code, lp, rp, comma, a, o, other = m.groups()
        if code:
            toks.append(("code", norm_code(code)))
        elif lp:
            toks.append(("(", lp))
        elif rp:
            toks.append((")", rp))
        elif comma:
            toks.append((",", comma))
        elif a:
            toks.append(("and", a))
        elif o:
            toks.append(("or", o))
        elif other and other.strip(" .;"):
            toks.append(("other", other.strip()))
    return toks


def _parse_expr(toks: list, i: int) -> tuple[tuple, int]:
    items, ops = [], []
    while i < len(toks):
        kind, val = toks[i]
        if kind == "(":
            node, i = _parse_expr(toks, i + 1)
            items.append(node)
            continue
        elif kind == ")":
            i += 1
            break
        elif kind == "code":
            items.append(("code", val))
        elif kind == "other":
            items.append(("other", val))
        elif kind in ("and", "or"):
            ops.append(kind)
        i += 1
    if len(items) == 1:
        return items[0], i
    op = "or" if "or" in ops and "and" not in ops else "and" if "and" in ops and "or" not in ops else ("or" if ops.count("or") >= ops.count("and") else "and")
    return (op, items), i


def _cnf(node) -> list[list[str]]:
    kind = node[0]
    if kind == "code":
        return [[node[1]]]
    if kind == "other":
        return [[OTHER]]
    children = [_cnf(c) for c in node[1]]
    if kind == "and":
        return [cl for ch in children for cl in ch]
    result: list[list[str]] = [[]]
    for ch in children:
        result = [r + cl for r in result for cl in ch][:40]
    return result


def parse_prereqs(text: str) -> tuple[list[list[str]], list[str]]:
    toks = _tokens(text)
    if not any(k == "code" for k, _ in toks):
        return [], [f"Non-course prerequisite: {text}"]
    node, _ = _parse_expr(toks, 0)
    groups, notes = [], []
    for g in _cnf(node):
        uniq = list(dict.fromkeys(g))
        if uniq == [OTHER]:
            continue
        groups.append(uniq)
    if any(k == "other" for k, _ in toks) and not any(OTHER in g for g in groups):
        notes.append("Includes a non-course condition (e.g. standing or 'any course at a level') that is not checked automatically.")
    if any(OTHER in g for g in groups):
        notes.append("Some prerequisites can be met by placement, test scores or standing; these cannot be verified automatically.")
    return groups, notes
