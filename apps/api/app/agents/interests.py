import json
import math
import re

from pydantic import BaseModel, Field

from app.agents.base import Agent, PlanContext
from app.agents.llm import structured_call, wrap_untrusted

# Deterministic interest matching (used when no LLM is available) is data-driven: TF-IDF
# cosine similarity between the student's own words and every course title/description
# in the catalog. There is no hand-written topic list, so no field or student is favored.
# Only standard acronyms are expanded so "AI" or "UX" can match course text.
ACRONYMS = {"ai": "artificial intelligence", "ml": "machine learning", "ux": "user experience", "ui": "user interface",
            "hci": "human computer interaction", "cs": "computer science", "it": "information technology",
            "i-o": "industrial organizational", "i/o": "industrial organizational", "pr": "public relations",
            "stem": "science technology engineering mathematics", "pre-med": "premedical medicine", "premed": "premedical medicine",
            "pre-law": "law legal", "esl": "english second language"}
SCORE_NOTE = "1.00 = the closest course description in Temple's catalog"

class ThemeOut(BaseModel):
    label: str
    evidence: str = Field(description="Short phrase quoted from the student's text")


class CourseScoreOut(BaseModel):
    course: str
    score: float = Field(description="0.0-1.0 relevance to the student's interests")
    reason: str = Field(description="One sentence citing what in the course description matches")
    matched_themes: list[str]


class InterestAnalysisOut(BaseModel):
    themes: list[ThemeOut]
    scores: list[CourseScoreOut]


STOP = set("""a an and are as at be but by for from has have i i'm im in into is it its me my of on or our so that the their them
this to too was we what when which with you your about also especially interested interest interests like love really want
studying study major minor how affects affect things stuff learn more course courses class classes maybe pursue
career careers work field fields want would future become get going plan planning someday eventually students student
topics topic area areas focus focused including include such other different various new using use used understand
introduction introductory principles advanced special selected seminar credit credits hours prerequisite prerequisites
required permission instructor department majors""".split())


def _stem(w: str) -> str:
    for suf in ("ational", "ations", "ation", "ities", "ness", "ments", "ment", "ings", "ing", "ies", "ers", "ed", "es", "s"):
        if len(w) - len(suf) >= 4 and w.endswith(suf):
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w


def _tokens(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z][a-z\-/]*", text.lower()):
        if w in ACRONYMS:
            out += ACRONYMS[w].split()
            continue
        for part in re.split(r"[-/]", w):
            if len(part) >= 3 and part not in STOP:
                out.append(_stem(part))
    return out


def _terms(text: str) -> list[str]:
    toks = _tokens(text)
    return toks + [f"{a} {b}" for a, b in zip(toks, toks[1:])]


def interest_terms(text: str) -> list[str]:
    return list(dict.fromkeys(_tokens(text)))


def detect_themes(text: str, boost_terms: list[str]) -> list[str]:
    """The student's own interest phrases (split on commas, 'and', 'or'), not a predefined topic list."""
    out = []
    for chunk in re.split(r"[,;.\n]|\band\b|\bor\b|\bbut\b|\bmaybe\b|\bespecially\b", f"{text} , {', '.join(boost_terms)}", flags=re.I):
        words = re.findall(r"[A-Za-z][A-Za-z\-/']*", chunk)
        while words and (words[0].lower() in STOP or words[0].lower() in {"in", "how"}):
            words = words[1:]
        while words and words[-1].lower() in STOP:
            words = words[:-1]
        if words and len(words) <= 6 and any(_tokens(w) for w in words):
            label = " ".join(words)
            label = label[0].upper() + label[1:]
            if label.lower() not in {o.lower() for o in out}:
                out.append(label)
    return out[:8]


class _Index:
    """TF-IDF index over the catalog's course titles (counted twice) and descriptions."""

    def __init__(self, courses: dict):
        self.docs: dict[str, dict[str, float]] = {}
        df: dict[str, int] = {}
        raw = {}
        for code, c in courses.items():
            title, desc = (c["title"], c["description"]) if isinstance(c, dict) else (c.title, c.description)
            tf: dict[str, float] = {}
            for t in _terms(f"{title} {title} {desc}"):
                tf[t] = tf.get(t, 0) + 1
            raw[code] = tf
            for t in tf:
                df[t] = df.get(t, 0) + 1
        n = max(1, len(courses))
        self.idf = {t: math.log((1 + n) / (1 + d)) + 1 for t, d in df.items()}
        for code, tf in raw.items():
            vec = {t: (1 + math.log(f)) * self.idf[t] for t, f in tf.items()}
            norm = math.sqrt(sum(v * v for v in vec.values())) or 1
            self.docs[code] = {t: v / norm for t, v in vec.items()}

    def query(self, text: str) -> dict[str, float]:
        tf: dict[str, float] = {}
        for t in _terms(text):
            if t in self.idf:
                tf[t] = tf.get(t, 0) + 1
        vec = {t: (1 + math.log(f)) * self.idf[t] for t, f in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1
        return {t: v / norm for t, v in vec.items()}

    def similarity(self, q: dict[str, float], code: str) -> tuple[float, list[str]]:
        d = self.docs.get(code, {})
        shared = [(t, q[t] * d[t]) for t in q if t in d]
        shared.sort(key=lambda x: -x[1])
        return sum(v for _, v in shared), [t for t, _ in shared]


_INDEX: dict[tuple, _Index] = {}


def catalog_index(courses: dict) -> _Index:
    key = (len(courses), min(courses, default=""), max(courses, default=""))
    if key not in _INDEX:
        _INDEX.clear()
        _INDEX[key] = _Index(courses)
    return _INDEX[key]


def fallback_scores(themes: list[str], courses: dict[str, dict], free_terms: list[str] | None = None,
                    index: _Index | None = None, text: str = "") -> dict[str, dict]:
    """Each of the student's interest phrases is matched separately (TF-IDF cosine, scaled so 1.0 is that
    phrase's best match in the whole catalog) and the per-phrase scores are combined with a noisy-OR:
    a course that matches several distinct interests ranks above one that repeats a single word."""
    index = index or _Index(courses)
    phrases = themes or [p for p in [text.strip()] if p]
    queries = []
    for ph in phrases:
        q = index.query(ph)
        if q:
            best = max((index.similarity(q, c)[0] for c in index.docs), default=0) or 1
            queries.append((ph, q, best))
    out = {}
    for code in courses:
        miss, parts, shared_all = 1.0, [], []
        for ph, q, best in queries:
            sim, shared = index.similarity(q, code)
            if sim <= 0:
                continue
            s_ph = min(1.0, sim / best)
            miss *= 1 - 0.8 * s_ph
            parts.append((ph, round(s_ph, 2), shared))
            shared_all += [t for t in shared if t not in shared_all]
        score = round(1 - miss, 3)
        parts.sort(key=lambda x: -x[1])
        if parts:
            reason = ("Matches " + "; ".join(f"'{ph}' {sv:.2f} via {', '.join(repr(t) for t in sh[:3])}" for ph, sv, sh in parts[:3])
                      + f". Each phrase is scored against its best match in Temple's catalog (1.00); combined {score:.2f}.")
        else:
            reason = "No overlap between the course description and your stated interests; included for degree progress."
        out[code] = {"score": score, "reason": reason, "matched_themes": [ph for ph, _, _ in parts], "method": "tfidf_similarity",
                     "matched_terms": shared_all[:8], "per_phrase": {ph: sv for ph, sv, _ in parts}}
    return out



class InterestMatchingAgent(Agent):
    key = "interest_matching"
    title = "Academic Interest Matching Agent"
    responsibility = "Interprets free-text interests and ranks requirement-eligible courses by semantic relevance to course descriptions."

    def run(self, ctx: PlanContext) -> dict:
        text = " ".join(x for x in (ctx.student.interests_text, ctx.student.career_interests) if x).strip()
        boosts = ctx.student.preferences.interest_boost_terms
        courses = ctx.state["course_discovery"]["courses"]
        scores: dict[str, dict] | None = None
        themes: list[dict] = []

        labels = detect_themes(text, boosts)
        # A phrase that only names one of the student's own programs ("I'm studying Psychology") matches every
        # course in that program, so it is not used to rank courses.
        program_words = {t for pid in ctx.student.program_ids for t in _tokens(ctx.catalog.programs.get(pid, {}).get("name", ""))}
        program_words |= {"major", "minor", "certificate"}
        named_programs = [l for l in labels if set(_tokens(l)) <= program_words]
        labels = [l for l in labels if l not in named_programs] or labels
        if named_programs:
            ctx.log("Interest phrases that only name your own program were not used for ranking", phrases=named_programs)
        index = catalog_index(ctx.catalog.courses)
        query = text + " " + " ".join(boosts)
        pre = fallback_scores(labels, courses, index=index, text=query)
        shortlist = sorted(courses, key=lambda k: -pre[k]["score"])[:80]
        catalog_blob = json.dumps([{"course": k, "title": courses[k]["title"], "description": courses[k]["description"]} for k in shortlist], indent=0)
        result = structured_call(
            system=("You are the Interest Matching Agent in a university academic planner. Identify the student's academic "
                    "interest themes and score how relevant each listed course is (0-1), using ONLY the course descriptions "
                    "provided. Score semantic relevance, not keyword overlap. Every course in the list must be scored exactly once."),
            user=(wrap_untrusted("student_interest_text", text + (f"\nAdditional emphasis requested: {', '.join(boosts)}" if boosts else ""))
                  + "\n\n" + wrap_untrusted("course_catalog", catalog_blob)),
            schema=InterestAnalysisOut,
        )
        if result is not None:
            valid = {s.course: s for s in result.scores if s.course in courses}
            if len(valid) >= len(shortlist) * 0.8:
                ctx.set_mode("llm")
                scores = {k: {"score": max(0.0, min(1.0, v.score)), "reason": v.reason,
                              "matched_themes": v.matched_themes, "method": "llm_semantic"} for k, v in valid.items()}
                for k in courses:
                    if k not in scores:
                        scores[k] = {**pre[k], "score": min(pre[k]["score"], 0.2)}
                themes = [{"label": t.label, "evidence": t.evidence} for t in result.themes]
                dropped = [s.course for s in result.scores if s.course not in courses]
                if dropped:
                    ctx.log("Discarded LLM scores for courses not in the dataset", courses=dropped)
            else:
                ctx.log("LLM output did not cover enough courses; using deterministic concept matching")
        if scores is None:
            ctx.set_mode("llm_fallback" if result is None and ctx.state.get("_llm_enabled") else "deterministic")
            themes = [{"label": l, "evidence": "phrase from your description"} for l in labels]
            scores = pre
        for code in courses:
            scores.setdefault(code, {"score": 0.0, "reason": "Not scored", "matched_themes": [], "method": "default"})
        for b in boosts:
            for code, c in courses.items():
                if b.lower() in (c["title"] + " " + c["description"]).lower():
                    scores[code]["score"] = min(1.0, scores[code]["score"] + 0.25)
                    scores[code]["reason"] += f" Boosted because you asked for more '{b}'."

        ranked = sorted(scores.items(), key=lambda kv: -kv[1]["score"])
        blocked = []
        for code, sc in ranked:
            info = courses[code]
            if sc["score"] >= 0.5 and info["prereq_status"] == "missing" and len(blocked) < 5:
                need = " and ".join(" or ".join(g) for g in info["prereq_missing"])
                blocked.append({"course": code, "title": info["title"], "score": sc["score"], "missing_prereq": need})
        ctx.log(f"Identified {len(themes)} interest themes", themes=[t["label"] for t in themes])
        ctx.log("Top matches", top=[f"{c} ({s['score']:.2f})" for c, s in ranked[:5]])
        if blocked:
            ctx.log("High-interest courses blocked by prerequisites (sent to Explanation Agent)", courses=[b["course"] for b in blocked])
        electives, enrichment = self._elective_search(ctx, labels, query, courses, index)
        for e in electives:
            scores[e["course"]] = {"score": e["score"], "reason": e["reason"], "matched_themes": e["matched_themes"], "method": e["method"]}
        enrichment = [{"course": b["course"], "title": b["title"], "score": b["score"], "reason": scores[b["course"]]["reason"],
                       "why_not": f"Prerequisite not completed: {b['missing_prereq']}"} for b in blocked] + enrichment
        if electives:
            ctx.log("Interest-based electives found outside your program requirements (free elective credit only)",
                    courses=[f"{e['course']} ({e['score']:.2f})" for e in electives])
        return {"themes": themes, "scores": scores, "ranking": [c for c, _ in ranked], "blocked_high_interest": blocked,
                "interest_electives": electives, "enrichment": enrichment[:8]}

    def _elective_search(self, ctx: PlanContext, labels: list[str], query: str, requirement_courses: dict, index) -> tuple[list[dict], list[dict]]:
        """Search the whole term catalog for courses that match the student's interests but are
        not tied to any of their requirements. These are labeled interest-based electives and are
        never presented as satisfying a degree requirement."""
        from app.agents.discovery import evaluate_course
        if not query.strip():
            return [], []
        catalog = ctx.catalog.courses
        done = {t.course for t in ctx.student.transcript if t.status in ("completed", "transfer", "in_progress")}
        by_course: dict[str, list] = {}
        for sec in ctx.catalog.sections:
            if sec.term_id == ctx.catalog.term_id:
                by_course.setdefault(sec.course, []).append(sec)
        pool = {code: {"title": catalog[code].title, "description": catalog[code].description}
                for code in by_course if code in catalog and code not in requirement_courses and code not in done
                and catalog[code].number < 5000}
        scored = fallback_scores(labels, pool, index=index, text=query)
        ranked = [c for c in sorted(pool, key=lambda k: -scored[k]["score"]) if scored[c]["score"] >= 0.45][:20]
        electives, enrichment = [], []
        excluded = set(ctx.student.preferences.excluded_courses)
        for code in ranked:
            ev = evaluate_course(catalog[code], by_course[code], ctx.student, excluded, ctx.catalog.term_name)
            base = {"course": code, "title": catalog[code].title, "score": scored[code]["score"], "reason": scored[code]["reason"],
                    "matched_themes": scored[code]["matched_themes"], "method": scored[code]["method"]}
            if ev["eligible"] and len(electives) < 6:
                electives.append({**base, "category": "INTEREST_ELECTIVE",
                                  "sections": [{**e, "requirement_ids": ["FREE_ELECTIVE"], "explicit": False} for e in ev["eligible"]]})
            elif not ev["eligible"] and len(enrichment) < 6:
                enrichment.append({**base, "why_not": ev["reason"]})
        return electives, enrichment

    def decision(self, ctx, o):
        disc = ctx.state.get("course_discovery", {})
        reqs = {r["id"]: r for r in ctx.state.get("degree_requirements", {}).get("requirements", [])}
        offered = {e["course"] for e in disc.get("eligible_sections", [])}
        checks = []
        for code in o["ranking"][:4]:
            info = disc.get("courses", {}).get(code, {})
            rnames = [reqs[r]["name"][:50] for r in info.get("requirement_ids", []) if r in reqs]
            checks.append(f"{code} ({o['scores'][code]['score']:.2f}): "
                          + (f"may satisfy {rnames[0]} (pending verification)" if rnames else "no requirement match")
                          + ("; eligible section available" if code in offered else f"; not schedulable ({'prerequisite' if info.get('prereq_status') == 'missing' else 'no eligible section'})"))
        method = next(iter(o["scores"].values()), {}).get("method", "n/a") if o["scores"] else "n/a"
        return {"task": "Interpret free-text interests and rank courses by relevance",
                "data_sources": ["Student interest text", "Bulletin course descriptions", f"Scoring method: {method}"],
                "findings": [f"Themes: {', '.join(t['label'] for t in o['themes']) or 'none'}", *checks,
                             f"{len(o.get('interest_electives', []))} interest-based elective(s) found outside requirements"],
                "recommendation": "Rank requirement courses by interest; offer non-requirement matches only as free electives.",
                "validation": {"status": "passed", "detail": "Cross-checked against requirement links (Requirements Agent) and sections (Discovery Agent)"},
                "unresolved": [f"{e['course']}: {e['why_not']}" for e in o.get("enrichment", [])[:4]]}

    def summarize(self, o: dict) -> str:
        top = ", ".join(o["ranking"][:3])
        return f"Themes: {', '.join(t['label'] for t in o['themes']) or 'none detected'}. Top matches: {top}."
