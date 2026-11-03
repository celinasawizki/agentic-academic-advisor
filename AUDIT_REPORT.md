# Audit report — Agentic Academic Advisor

Status: **partially complete** (work stopped at a usage limit). Raw evidence: [docs/audit/reproduction-before.md](docs/audit/reproduction-before.md), captured against the running API at commit 48d0752.

## Confirmed bugs (reproduced) and fixes

| # | Finding (evidence) | Fix | Regression test |
|---|---|---|---|
| 1 | Real student records readable, modifiable, plannable, exportable and deletable with **no credentials**; demo advisor role could review a **real** plan (all returned 200) | `app/core/auth.py`: pluggable `AuthProvider` (prototype per-student bearer token, hash-only storage; `TempleSSOProvider` stub). Every student/plan/export endpoint authorizes via record ownership; demo advisor limited to fictional students; denials return 404 | `test_real_records_require_owner_and_demo_advisor_is_fictional_only`, onboarding test |
| 2 | Manual validation counted lecture + lab of 4-credit PHYS 1021 as **8 credits**; validation didn't know section components | Components assigned once in the catalog adapter (`app/ingest/sections.py`); validation uses the same `review_sections` as the Review Agent with component-aware credits | `test_lecture_lab_credits_not_double_counted` |
| 3 | Lecture/lab pairing presented as certain, though Temple publishes no linkage (0/8,690 sections linked) | Pairing labeled *inferred/unverified* in review checks and explanations; missing components are warnings, not invented requirements | review checks |
| 4 | 2,194 variable-credit sections silently planned at their minimum | Warning and explanation note showing the assumed credit | review checks |
| 5 | Grades F/W/D satisfied prerequisites and requirements despite the bulletin's "minimum grade of C-" | Minimum-grade parsing, non-passing grades excluded, GenEd C- rule | `test_failing_and_below_minimum_grades_do_not_count` |
| 6 | "Preferred" class times ignored by the optimizer | Soft penalty for sections outside preferred windows | `test_preferred_times_shape_soft_penalty` |
| 7 | Two simultaneous change requests both started runs (race) | Atomic conditional claim (`UPDATE … WHERE status != 'running'`) before any state is written; 409 otherwise | `test_busy_plan_rejects_second_change` |
| 8 | Preference changes lost when a new plan starts | Persisted to the owning real student's record (demo records stay shared and unchanged) | `test_preferences_persist_for_real_students` |

## Improvements implemented
- Requirement reliability statuses **VERIFIED / PENDING_VERIFICATION / AMBIGUOUS / UNAVAILABLE / BLOCKED**. VERIFIED comes only from a human registry (`data/temple/verifications.json`, empty).
- Course categories: REQUIRED / DEGREE_ELECTIVE / INTEREST_ELECTIVE, with optional enrichment listed separately. The Interest agent now searches the whole term catalog for interest-based electives, which are never presented as requirement credit; they are capped per strategy.
- Per-course explanation: alternatives considered with reasons, an explicit "unverified" list, and full provenance (term, CRN, campus, modality, meetings, source, retrieval date, "seats as of snapshot, not live").
- The no-perfect-schedule headline is built from the solver's conflict set. New endpoints: `POST /plans/{id}/resolve` (accept a verified tradeoff; hard availability and F-1 can't be relaxed there) and `POST /plans/{id}/regenerate`.
- Mock TUportal export requires `student_approved`; live-availability adapter interface added (not configured: requires Temple authorization).
- Career interests field on onboarding (API).

## Test results
`pytest tests -q`: **58 passed** (was 52). Frontend: `tsc` and `eslint` clean. The production build and browser e2e were **not re-run** after these changes.

## Remaining (not done yet)
- Frontend for the new features: requirement-status legend, category badges, alternatives and unverified lists in the course panel, "Accept tradeoff" / "Regenerate" buttons, approval dialog before export (the Save button currently sends approval implicitly), career-interest and days-off controls in onboarding.
- Structured agent **decision log** (`AgentExecution.decision` column exists, not populated yet).
- Tests for interest electives, the resolve/regenerate endpoints, requirement statuses, multi-program and unavailable-course scenarios.
- README / demo walkthrough refresh; re-run the build and browser e2e.

## Requires Temple authorization
Temple SSO (identity plus advisor assignment), Degree Audit access, a live seat/availability feed, the TUportal test environment, and a curated verification of requirement rules. This prototype is not FERPA-reviewed.

## Run
API: `cd apps/api && .venv/bin/uvicorn app.main:app --port 8010` (existing SQLite DBs migrate additively). Web: `cd apps/web && npm run dev` with `NEXT_PUBLIC_API_URL=http://127.0.0.1:8010`.
