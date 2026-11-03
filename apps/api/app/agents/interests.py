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


def fallback_scores(themes: list[str], courses: dict[str, dict]) -> dict[str, dict]:
    out = {}
    for code, c in courses.items():
        title, desc = c["title"].lower(), c["description"].lower()
        miss_prob, matched, evidence = 1.0, [], []
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
                  if matched else "No clear overlap with your stated interests; included for degree progress.")
        out[code] = {"score": score, "reason": reason, "matched_themes": matched, "method": "concept_expansion"}
    return out


class InterestMatchingAgent(Agent):
    key = "interest_matching"
    title = "Academic Interest Matching Agent"
    responsibility = "Interprets free-text interests and ranks requirement-eligible courses by semantic relevance to course descriptions."

    def run(self, ctx: PlanContext) -> dict:
        text = ctx.student.interests_text or ""
        boosts = ctx.student.preferences.interest_boost_terms
        courses = ctx.state["course_discovery"]["courses"]
        scores: dict[str, dict] | None = None
        themes: list[dict] = []

        catalog_blob = json.dumps([{"course": k, "title": v["title"], "description": v["description"]} for k, v in courses.items()], indent=0)
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
            if len(valid) >= len(courses) * 0.8:
                ctx.set_mode("llm")
                scores = {k: {"score": max(0.0, min(1.0, v.score)), "reason": v.reason,
                              "matched_themes": v.matched_themes, "method": "llm_semantic"} for k, v in valid.items()}
                themes = [{"label": t.label, "evidence": t.evidence} for t in result.themes]
                dropped = [s.course for s in result.scores if s.course not in courses]
                if dropped:
                    ctx.log("Discarded LLM scores for courses not in the dataset", courses=dropped)
            else:
                ctx.log("LLM output did not cover enough courses; using deterministic concept matching")
        if scores is None:
            ctx.set_mode("llm_fallback" if result is None and ctx.state.get("_llm_enabled") else "deterministic")
            labels = detect_themes(text, boosts)
            themes = [{"label": l, "evidence": "matched from your description"} for l in labels]
            scores = fallback_scores(labels, courses)
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
            if sc["score"] >= 0.5 and info["prereq_status"] == "missing":
                need = " and ".join(" or ".join(g) for g in info["prereq_missing"])
                blocked.append({"course": code, "title": info["title"], "score": sc["score"], "missing_prereq": need})
        ctx.log(f"Identified {len(themes)} interest themes", themes=[t["label"] for t in themes])
        ctx.log("Top matches", top=[f"{c} ({s['score']:.2f})" for c, s in ranked[:5]])
        if blocked:
            ctx.log("High-interest courses blocked by prerequisites (sent to Explanation Agent)", courses=[b["course"] for b in blocked])
        return {"themes": themes, "scores": scores, "ranking": [c for c, _ in ranked], "blocked_high_interest": blocked}

    def summarize(self, o: dict) -> str:
        top = ", ".join(o["ranking"][:3])
        return f"Themes: {', '.join(t['label'] for t in o['themes']) or 'none detected'}. Top matches: {top}."
