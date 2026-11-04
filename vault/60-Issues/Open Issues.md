---
tags: [issues]
---
# Open Issues
Update when fixed (link the commit) or move to [[Known Limitations]] if accepted.

## Stress test: course scheduled together with its own prerequisite
Source: `docs/audit/stress-report.json` (seed 42, 400 students, **3 violations**; may predate current uncommitted changes — re-run to confirm).
- `chinese-ba` + `environmental-engineering-minor`: SPAN 1003 with prereq SPAN 1002 (graduation, balance, after regenerate, after "No classes before 10am")
- `information-science-technology-ba` + `finance-minor`: FIN 3507 with prereq FIN 3504 (interest, balance)
- `natural-sciences-chemistry-ba`: SCTC 3312 with prereq BIOL 1111 (graduation; after "12 credits"; after regenerate)

Suspect: eligibility treats a prereq as satisfiable by a course in the *same* schedule, or an in-progress/planned item counts as completed. Check [[Course Discovery Agent]], [[Academic Review Agent]], `rules.py` prereq check.

## Uncommitted work (2026-11-03)
Changes in constraints, explanation, graduation, optimization agents, `optimizer.py`, `routers/plans.py`, explain/schedules pages, `test_school_layers.py`; new `apps/api/scripts/stress_plans.py`. Not yet committed.
