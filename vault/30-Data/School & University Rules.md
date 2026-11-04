# School & University Rules
`data/temple/school_rules.json`, parser `apps/api/app/ingest/school.py`, tests `tests/test_school_layers.py`.

- 13 undergraduate schools/colleges, each rule with a verbatim bulletin quote (checked live by [[Requirements Research Agent]]). Examples: Liberal Arts 123 credits / 45 upper-level / BA language through 1002; Fox 20-course BBA core; Klein KLN 1001/1002, 124 credits; CST SCTC 1001; HRPR 1001 for Public Health & Social Work.
- University: 30-credit residency, two WI courses (exact WI list from each major's page), program minimum grades.
- Applied automatically by program type and degree (BA / BS / BBA).
- Sweep: `python -m scripts.sweep_programs` → 436/436 complete at `673fd59`.
