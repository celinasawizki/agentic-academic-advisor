---
tags: [moc, agents]
---
# Agents Index
Pipeline order (files in `apps/api/app/agents/`). Agents talk only through typed state in [[Orchestrator & Shared State]]; each writes a decision record (task, sources, findings, recommendation, validation, unresolved).

| # | Agent | File | Engine |
|---|---|---|---|
| 1 | [[Academic Profile Agent]] | `profile.py` | Deterministic |
| 2 | [[Requirements Research Agent]] | `research.py` | Deterministic + optional Claude search |
| 3 | [[Degree Requirements Agent]] | `requirements.py` | Deterministic |
| 4 | [[Course Discovery Agent]] | `discovery.py` | Deterministic |
| 5 | [[Interest Matching Agent]] | `interests.py` | Claude or concept fallback |
| 6 | [[Graduation Planning Agent]] | `graduation.py` | Deterministic |
| 7 | [[Scheduling Constraints Agent]] | `constraints.py` | Deterministic |
| 8 | [[Schedule Optimization Agent]] | `optimization.py` | CP-SAT |
| 9 | [[Academic Review Agent]] | `review.py` | Deterministic |
| 10 | [[Student Explanation Agent]] | `explanation.py` | Templated + optional Claude |

Shared: `base.py` (Agent, Catalog, PlanContext), `categories.py` (course roles), `llm.py`.
