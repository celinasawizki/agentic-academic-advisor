"""School/college and university requirement layers.

A program's own bulletin page lists only its major/minor/certificate courses.
Graduation also depends on the student's school (e.g. CLA's foreign language and
professional-development seminar, Klein's KLN 1001/1002, the Fox business core)
and on university rules (residency, writing-intensive courses). Those come from
data/temple/school_rules.json, transcribed from each school's bulletin page with
a verbatim evidence quote, plus facts parsed from each program page's
"Summary of Requirements" prose. Every quote is checked against the fetched page
so a rule whose source text changed is flagged instead of silently applied.

Used by scripts/ingest_bulletin.py (snapshot) and the Requirements Research
Agent (live pages at plan time)."""

import hashlib
import html as htmllib
import json
import re
from collections.abc import Callable
from pathlib import Path

from app.ingest.bulletin import CODE, CODE_RE, DEGREE_SUFFIX, clean, parse_requirement_tables, section_html

LAYER_TYPES = ("school", "university")
WI_RE = re.compile(r"writing[- ]intensive", re.I)
CREDITS_RE = re.compile(r"(?:minimum of|total of|completion of|requires?|require)\s+(?:a minimum of\s+)?(\d{3})\s+(?:total\s+)?"
                        r"(?:credits|credit hours|semester hours|s\.h\.)|\((\d{3}) total s\.h\.\)", re.I)
MIN_GRADE_RE = re.compile(r"(?:minimum grade of|minimum grades of|grade of at least|grades? of)\s+\"?(B-|C\+|C-|C|D\+|D-|D)\"?(?![A-Za-z+-])", re.I)
GRADE_SCOPE_RE = re.compile(r"\b(each|all|every|required|major|minor|certificate)\b", re.I)


def norm(text: str) -> str:
    """Whitespace-, case- and quote-insensitive form used to compare evidence with page text."""
    t = htmllib.unescape(text).replace("“", '"').replace("”", '"').replace("’", "'").replace("–", "-")
    return re.sub(r"\s+", "", t).lower()


def load_spec(data_dir: Path) -> dict:
    f = data_dir / "school_rules.json"
    return json.loads(f.read_text()) if f.exists() else {"layers": []}


def degree_of(program_id: str) -> str | None:
    m = DEGREE_SUFFIX.search(program_id)
    return m.group(1) if m else None


def college_of(program: dict) -> str | None:
    m = re.match(r"https?://[^/]+/undergraduate/([^/]+)/", program.get("source_url") or "")
    return m.group(1) if m else None


def applies(cond: dict | None, program: dict) -> bool:
    if not cond:
        return True
    if "types" in cond and program["type"] not in cond["types"]:
        return False
    if "degrees" in cond and degree_of(program["id"]) not in cond["degrees"]:
        return False
    if "name_matches" in cond and not re.search(cond["name_matches"], program["name"]):
        return False
    if "name_excludes" in cond and re.search(cond["name_excludes"], program["name"]):
        return False
    return program["id"] not in cond.get("exclude", [])


def language_subjects(courses: dict, include_asl: bool = False) -> list[str]:
    """Subjects whose 1001/1002 courses are an introductory language sequence, derived from course descriptions."""
    out = []
    for code, c in courses.items():
        subj, num = code.split()
        if num != "1002" or f"{subj} 1001" not in courses:
            continue
        first = courses[f"{subj} 1001"]
        text = " ".join(str(x) for x in (_get(c, "title"), _get(c, "description"), _get(first, "description"))).lower()
        if re.search(r"\b(grammar|vocabulary|pronunciation|conversation|speaking|spoken|elements|elementary)\b", text):
            out.append(subj)
    asl = [s for s in out if "sign language" in str(_get(courses[f"{s} 1002"], "title")).lower()]
    return sorted(s for s in out if include_asl or s not in asl)


def _get(c, key: str):
    return c.get(key) if isinstance(c, dict) else getattr(c, key, None)


def _slice_by_headings(container: str, start: str, end: str) -> str:
    heads = [(m.start(), clean(m.group(1))) for m in re.finditer(r"<h[2-5][^>]*>(.*?)</h[2-5]>", container, re.S)]
    i = next((pos for pos, t in heads if t == start), None)
    if i is None:
        return ""
    j = next((pos for pos, t in heads if pos > i and t == end), len(container))
    return container[i:j]


def _paragraphs(container: str) -> list[str]:
    return [m.group(0) for m in re.finditer(r"<(p|li)\b[^>]*>.*?</\1>", container, re.S)]


def summary_facts(page: str) -> dict:
    """Facts stated in a program page's requirement prose (not its course tables)."""
    req = section_html(page, "requirementstextcontainer") or section_html(page, "textcontainer")
    prose = re.sub(r"<table class=\"sc_courselist.*?</table>", " ", req, flags=re.S)
    text = clean(prose)
    facts: dict = {}
    for m in CREDITS_RE.finditer(text):
        n = int(m.group(1) or m.group(2))
        if 115 <= n <= 140:
            facts["total_credits"] = {"needed": n, "evidence": text[max(0, m.start() - 60): m.end() + 20].strip()}
            break
    for sentence in re.split(r"(?<=[.;])\s+", text):
        if "prerequisite" in sentence.lower() or not GRADE_SCOPE_RE.search(sentence):
            continue
        m = MIN_GRADE_RE.search(sentence)
        if m:
            facts["min_grade"] = {"grade": m.group(1).upper(), "evidence": sentence.strip()[:300]}
            break
    for para in _paragraphs(req):
        inner = para.find("<table")
        ptext = clean(para[:inner] if inner >= 0 else para)
        if not WI_RE.search(ptext):
            continue
        codes = list(dict.fromkeys(CODE_RE.findall(ptext)))
        if inner >= 0:  # the course list is nested inside the same list item
            table = para[inner:]
        else:
            end = req.find(para) + len(para)
            nxt = re.match(r"\s*(?:<[^t][^>]*>\s*)*(<table class=\"sc_courselist.*?</table>)", req[end:end + 20000], re.S)
            table = nxt.group(1) if nxt and ptext.rstrip().endswith(":") else ""
        codes += [c for c in dict.fromkeys(re.findall(CODE, clean(table))) if c not in codes]
        facts["writing_intensive"] = {"codes": codes, "evidence": ptext[:400]}
        break
    return facts


WI_POLICY_URL = "https://bulletin.temple.edu/undergraduate/writing-intensive-courses/"
WI_POLICY_EVIDENCE = "All undergraduate students must complete at least two writing-intensive courses for a total of at least six credits."


def _rule_dict(prog_id: str, layer: dict, rule: dict, courses: dict, section_html_text: str, page_norm: str | None) -> dict:
    options = [list(o) for o in rule.get("options", [])]
    patterns = [dict(p) for p in rule.get("patterns", [])]
    if rule.get("language_level"):
        level = rule["language_level"]
        options += [[f"{s} {level}"] for s in language_subjects(courses, rule.get("include_asl", False)) if f"{s} {level}" in courses]
    if rule.get("table") and section_html_text:
        for r in parse_requirement_tables(_slice_by_headings(section_html_text, rule["table"]["from"], rule["table"]["to"])):
            options += [o for o in r.options if o not in options]
    if rule.get("metric"):
        patterns = [{"metric": rule["metric"]}]
    found = page_norm is None or norm(rule["evidence"]) in page_norm
    notes = list(rule.get("notes", []))
    if not found:
        notes.append("The bulletin text this rule was transcribed from was not found on the current page; it may have changed.")
    return {"id": f"{prog_id}-{rule['id']}", "group": layer["name"], "name": rule["name"], "kind": rule["kind"],
            "needed": rule.get("needed", 0), "options": options, "patterns": patterns, "notes": notes,
            "evidence": rule["evidence"], "evidence_found": found,
            "verification_status": "parsed" if found else "needs_review"}


def build_layers(spec: dict, programs: list[dict], courses: dict, get_page: Callable[[str], str | None],
                 retrieved_at: str | None = None) -> dict:
    """Materialize the school/university layers that apply to the given programs.

    Returns {"layers": [layer program dicts], "links": {program_id: [layer ids]},
             "min_grades": {program_id: {...}}, "checks": [...evidence checks...]}."""
    layers: dict[str, dict] = {}
    links: dict[str, list[str]] = {}
    min_grades: dict[str, dict] = {}
    checks: list[dict] = []
    pages: dict[str, str | None] = {}

    def fetch(url: str) -> str | None:
        base = url.split("#")[0]
        if base not in pages:
            pages[base] = get_page(base)
        return pages[base]

    for prog in programs:
        if prog["type"] not in ("major", "minor", "certificate"):
            continue
        college = college_of(prog)
        mine: list[str] = []
        for layer in spec.get("layers", []):
            if layer.get("college") not in (None, college) or not applies(layer.get("applies"), prog):
                continue
            page = fetch(layer["url"])
            section = section_html(page, layer["container"]) if page and layer.get("container") else (page or "")
            page_norm = norm(clean(section)) if page else None
            rules = [r for r in layer["rules"] if applies(r.get("applies"), prog)]
            conditional = sorted(r["id"] for r in rules if r.get("applies"))
            lid = f"layer-{layer['id']}" + (f"--{'.'.join(conditional)}" if conditional else "")
            if layer.get("min_grade"):
                mg = layer["min_grade"]
                ok = page_norm is None or norm(mg["evidence"]) in page_norm
                min_grades.setdefault(prog["id"], {"grade": mg["grade"], "evidence": mg["evidence"], "source_url": layer["url"],
                                                   "evidence_found": ok})
            if lid not in layers:
                reqs = [_rule_dict(lid, layer, r, courses, section, page_norm) for r in rules]
                if layer.get("tables") and section:
                    t = layer["tables"]
                    for j, r in enumerate(parse_requirement_tables(_slice_by_headings(section, t["from"], t["to"])), 1):
                        d = r.to_dict()
                        if d["kind"] == "note":
                            continue
                        for ov in layer.get("overrides", []):
                            if re.search(ov["match"], d["name"]):
                                d.update(kind=ov["kind"], needed=ov["needed"], options=[], verification_status="parsed",
                                         patterns=[{"subject": s, "min": ov["min"], "max": ov["max"]} for s in ov["subjects"]],
                                         notes=[f"Bulletin: \"{ov['evidence']}\""])
                        d.update(id=f"{lid}-t{j}", group=f"{layer['name']}: {d['group']}", evidence=t["evidence"],
                                 evidence_found=page_norm is None or norm(t["evidence"]) in page_norm)
                        reqs.append(d)
                for r in reqs:
                    checks.append({"layer": lid, "rule": r["id"], "url": layer["url"], "found": r["evidence_found"]})
                layers[lid] = {
                    "id": lid, "name": layer["name"] + (f" ({(degree_of(prog['id']) or '').upper()})" if any("degrees" in (r.get("applies") or {}) for r in rules) else ""),
                    "type": "university" if layer.get("college") is None else "school", "college": prog["college"] if layer.get("college") else "Temple University",
                    "catalog_year": spec.get("_meta", {}).get("catalog_year"), "source_url": layer["url"], "retrieved_at": retrieved_at,
                    "total_credit_hours": [], "supported": True, "requirements": reqs,
                }
            mine.append(lid)

        if prog["type"] == "major":
            page = fetch(prog["source_url"])
            facts = summary_facts(page) if page else {}
            lid = f"{prog['id']}--degree"
            reqs = []
            wi = facts.get("writing_intensive")
            if wi and wi["codes"]:
                evidence, found, codes = wi["evidence"], True, wi["codes"]
                notes = ["Met by the listed writing-intensive courses of your major; they must be taken at Temple."]
            else:  # the program page does not name its WI courses: fall back to the university policy
                policy = fetch(WI_POLICY_URL)
                evidence, codes = WI_POLICY_EVIDENCE, []
                found = policy is None or norm(WI_POLICY_EVIDENCE) in norm(clean(policy))
                notes = ["This program's page does not list its writing-intensive courses; any course with the WI attribute is counted. "
                         "Your major specifies which WI courses apply — confirm with your advisor."]
            reqs.append({"id": f"{lid}-wi", "group": "Temple University requirements", "kind": "milestone", "needed": 2,
                         "name": "Two writing-intensive (WI) courses in the major", "options": [[c] for c in codes],
                         "patterns": [{"metric": "wi_courses"}], "notes": notes, "evidence": evidence, "evidence_found": found,
                         "verification_status": "parsed" if codes and found else "needs_review"})
            checks.append({"layer": lid, "rule": f"{lid}-wi", "url": prog["source_url"] if codes else WI_POLICY_URL, "found": found})
            school_credits = {r["needed"] for x in mine for r in layers[x]["requirements"]
                              if r["kind"] == "milestone" and r["patterns"] == [{"metric": "total_credits"}]}
            tc = facts.get("total_credits")
            if tc and tc["needed"] not in school_credits:
                reqs.append({"id": f"{lid}-credits", "group": "Temple University requirements", "kind": "milestone", "needed": tc["needed"],
                             "name": f"Minimum {tc['needed']} credits for the degree", "options": [], "patterns": [{"metric": "total_credits"}],
                             "notes": [], "evidence": tc["evidence"], "evidence_found": True, "verification_status": "parsed"})
            if reqs:
                layers[lid] = {"id": lid, "name": f"Degree requirements stated on the {prog['name']} page", "type": "university",
                               "college": prog["college"], "catalog_year": prog.get("catalog_year"), "source_url": prog["source_url"],
                               "retrieved_at": retrieved_at, "total_credit_hours": [], "supported": True, "requirements": reqs}
                mine.append(lid)
        if page := fetch(prog["source_url"]):
            mg = summary_facts(page).get("min_grade")
            if mg:  # the program's own statement takes precedence over its school's default
                min_grades[prog["id"]] = {**mg, "source_url": prog["source_url"], "evidence_found": True}
        links[prog["id"]] = mine
    return {"layers": list(layers.values()), "links": links, "min_grades": min_grades, "checks": checks}


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]
