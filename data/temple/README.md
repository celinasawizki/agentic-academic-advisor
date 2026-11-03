# Temple data snapshot

| File | Source | Retrieved | Notes |
|---|---|---|---|
| `programs.json` | [Temple Academic Bulletin](https://bulletin.temple.edu/undergraduate/) program pages (requirements tab), 2026-2027 catalog | see `_meta.generated_at` and per-program `retrieved_at` | 435 undergraduate majors, minors and certificates + GenEd framework. Parsed by `apps/api/app/ingest/bulletin.py`. |
| `courses.json` | Bulletin course descriptions (`/courses/<subject>/`) | `_meta.generated_at` | Undergraduate courses (numbered below 5000): credits, GenEd attributes, prerequisite text and parsed AND/OR groups. |
| `sections-202703.json` | Temple public class search (Banner SSB), Spring 2027 | `_meta.retrieved_at` | One-time snapshot taken with the project owner's approval, 1 request/second. |
| `students.json` | — | — | **Fictional** demo students using real program and course codes. |

## How requirements are represented

Each program has ordered rules:

- `kind: "count"` — take `needed` of the listed `options`. An option is a list of courses that must all be taken (e.g. `["CHEM 1031", "CHEM 1033"]`, a lecture and its lab). Bulletin "or" rows become extra options.
- `kind: "credits"` — earn `needed` credits from the options ("Select 9 credits from the following").
- `patterns` — course ranges (`{"subject": "PSY", "min": 3000, "max": 3620}`) or GenEd attributes (`{"attribute": "GA"}`) that also satisfy the rule.
- `kind: "manual"` — free-text rules the parser could not interpret. Shown to students as "manual review"; never guessed.
- `kind: "note"` — footnote legends, alternative tracks ("select one lab science sequence"), and supplementary lists after a program's credit total. Kept for reference only.

Prerequisites are stored as an AND of OR-groups. `@OTHER` marks an alternative that is not a course (placement test, standing) and cannot be verified automatically.

## Accuracy

Parsing is automatic. Every requirement is labeled "pending verification" in the app, and students are told to confirm with their official degree audit and advisor. Known gaps: earlier catalog years (bulletin archives are excluded by robots.txt), substitutions approved outside the bulletin, and rules written as prose.
