import json
import re

from pydantic import BaseModel, Field

from app.agents.base import Agent, PlanContext
from app.agents.llm import structured_call, wrap_untrusted

# Concept expansion used when no LLM is available. Each theme maps phrases a
# student might write to vocabulary that appears in course descriptions.
THEMES: dict[str, dict] = {
    "Industrial-Organizational Psychology": {
        "triggers": ["industrial", "organizational", "i-o", "i/o", "workplace", "work behavior", "employee", "leadership", "organizational behavior"],
        "terms": ["industrial", "industrial-organizational", "workplace", "work", "organizational", "organizations", "personnel", "employee", "leadership", "teams", "job", "motivation", "engagement", "performance", "training", "burnout"],
    },
    "Artificial Intelligence": {
        "triggers": ["artificial intelligence", " ai", "ai ", "machine learning", "algorithm"],
        "terms": ["artificial intelligence", "ai", "machine learning", "neural networks", "algorithms", "automation", "intelligent"],
    },
    "Human-Technology Interaction": {
        "triggers": ["technology", "human-computer", "hci", "ux", "interface", "human factors"],
        "terms": ["technology", "interface", "usability", "human-computer", "interact", "user-centered", "automation", "digital", "trust", "human factors"],
    },
    "Decision Making": {
        "triggers": ["decision", "judgment", "choice"],
        "terms": ["decision", "decisions", "judgment", "heuristics", "biases", "choice", "reasoning", "uncertainty"],
    },
    "Clinical Psychology": {
        "triggers": ["clinical", "therapy", "mental health", "disorder", "counsel"],
        "terms": ["clinical", "psychotherapy", "disorders", "assessment", "treatment"],
    },
    "Neuroscience": {
        "triggers": ["neuro", "brain"],
        "terms": ["neural", "brain", "neuroimaging", "neuroscience", "biological"],
    },
    "Entrepreneurship & Business": {
        "triggers": ["entrepreneur", "startup", "business", "venture", "innovation"],
        "terms": ["venture", "ventures", "startup", "startups", "entrepreneurial", "business", "innovation", "market"],
    },
    "Finance": {"triggers": ["finance", "financial", "invest"], "terms": ["finance", "financing", "valuation", "capital", "financial"]},
    "Marketing": {"triggers": ["marketing", "consumer", "brand"], "terms": ["marketing", "consumer", "segmentation", "brand"]},
    "Data Science": {
        "triggers": ["data", "statistics", "analytics"],
        "terms": ["data", "statistical", "statistics", "modeling", "visualization", "regression", "machine learning"],
    },
    "Research Methods": {"triggers": ["research", "methods", "experiment"], "terms": ["research", "methods", "experimental", "measurement", "survey"]},
}


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


def detect_themes(text: str, boost_terms: list[str]) -> list[str]:
    t = f" {text.lower()} "
    found = [label for label, th in THEMES.items() if any(trig in t for trig in th["triggers"])]
    for b in boost_terms:
        bl = f" {b.lower()} "
        found += [label for label, th in THEMES.items() if label not in found and any(trig in bl for trig in th["triggers"])]
    return found


def _hits(terms: list[str], text: str) -> list[str]:
    return [term for term in terms if re.search(rf"\b{re.escape(term)}\b", text)]


STOP = set("""a an and are as at be but by for from has have i i'm im in into is it its me my of on or our so that the their them
this to too was we what when which with you your about also especially interested interest interests like love really want
studying study major minor how affects affect things stuff learn learning more course courses class classes""".split())


def interest_terms(text: str) -> list[str]:
    words = re.findall(r"[a-z][a-z\-]{3,}", text.lower())
    return list(dict.fromkeys(w for w in words if w not in STOP))


def fallback_scores(themes: list[str], courses: dict[str, dict], free_terms: list[str] | None = None) -> dict[str, dict]:
    out = {}
    free_terms = free_terms or []
    for code, c in courses.items():
        title, desc = c["title"].lower(), c["description"].lower()
        miss_prob, matched, evidence = 1.0, [], []
        free_hits = [t for t in free_terms if re.search(rf"\b{re.escape(t)}", title + " " + desc)]
        if free_hits:
            miss_prob *= 1 - min(0.6, 0.2 * len(free_hits))
            evidence += free_hits
        for label in themes:
            terms = THEMES[label]["terms"]
            h_title, h_desc = _hits(terms, title), _hits(terms, desc)
            strength = min(1.0, (2 * len(h_title) + len(set(h_desc) - set(h_title))) / 4)
            if strength > 0:
                miss_prob *= 1 - 0.85 * strength
                matched.append(label)
                evidence += [h for h in h_title + h_desc if h not in evidence]
        score = round(1 - miss_prob, 3)
        reason = (f"Course description covers {', '.join(repr(e) for e in evidence[:4])}, related to your interest in {', '.join(matched)}."
                  if matched else f"Course description mentions {', '.join(repr(e) for e in evidence[:4])} from your interests."
                  if evidence else "No clear overlap with your stated interests; included for degree progress.")
        out[code] = {"score": score, "reason": reason, "matched_themes": matched, "method": "concept_expansion"}
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
        pre = fallback_scores(labels, courses, interest_terms(text + " " + " ".join(boosts)))
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
            themes = [{"label": l, "evidence": "matched from your description"} for l in labels]
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
        electives, enrichment = self._elective_search(ctx, labels, interest_terms(text + " " + " ".join(boosts)), courses)
        for e in electives:
            scores[e["course"]] = {"score": e["score"], "reason": e["reason"], "matched_themes": e["matched_themes"], "method": e["method"]}
        enrichment = [{"course": b["course"], "title": b["title"], "score": b["score"], "reason": scores[b["course"]]["reason"],
                       "why_not": f"Prerequisite not completed: {b['missing_prereq']}"} for b in blocked] + enrichment
        if electives:
            ctx.log("Interest-based electives found outside your program requirements (free elective credit only)",
                    courses=[f"{e['course']} ({e['score']:.2f})" for e in electives])
        return {"themes": themes, "scores": scores, "ranking": [c for c, _ in ranked], "blocked_high_interest": blocked,
                "interest_electives": electives, "enrichment": enrichment[:8]}

    def _elective_search(self, ctx: PlanContext, labels: list[str], terms: list[str], requirement_courses: dict) -> tuple[list[dict], list[dict]]:
        """Search the whole term catalog for courses that match the student's interests but are
        not tied to any of their requirements. These are labeled interest-based electives and are
        never presented as satisfying a degree requirement."""
        from app.agents.discovery import evaluate_course
        if not labels and not terms:
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
        scored = fallback_scores(labels, pool, terms)
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

    def summarize(self, o: dict) -> str:
        top = ", ".join(o["ranking"][:3])
        return f"Themes: {', '.join(t['label'] for t in o['themes']) or 'none detected'}. Top matches: {top}."
