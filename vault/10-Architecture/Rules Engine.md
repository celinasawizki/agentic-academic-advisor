# Rules Engine
File: `apps/api/app/rules.py`. Deterministic; the authority on validity ([[ADR-001 LLMs never decide validity]]).

- Requirement matching: count/credits rules, "or" options, lecture+lab bundles, ranges, GenEd attributes; no double counting without a rule.
- Prerequisites: AND of OR-groups; `@OTHER` = non-course alternative (placement, standing) → can't auto-verify. In-progress ≠ completed.
- Grades: F, W, D don't satisfy; minimum prereq grades and GenEd C- enforced (audit B7). Prose "C- in major" rules are **not** enforced yet → [[Known Limitations]].
- F-1 counting: configurable via `F1_FULL_TIME_CREDITS`, `F1_MAX_ONLINE_CREDITS_COUNTED`, `F1_HYBRID_COUNTS_AS_IN_PERSON`.
- `review_sections` is shared by the Review Agent and manual `/validate` (audit B4).

Related: [[Requirement Model]], [[School & University Rules]].
