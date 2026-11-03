# Audit report — Agentic Academic Advisor

Audited from commit `48d0752`. Every finding below was reproduced before it was fixed. Raw evidence:
[docs/audit/reproduction-before.md](docs/audit/reproduction-before.md) (live API + rule-level reproductions) and
[docs/audit/reproduction-after.md](docs/audit/reproduction-after.md) (the same scenarios after the fixes).

## 1. Confirmed bugs

| # | Area | Finding and evidence (before) | After |
|---|---|---|---|
| B1 | Security | A real student's record could be read, planned, modified, exported and deleted with **no credentials** (all returned 200) | 404 without the owner's credential; owner gets 200 |
| B2 | Security | The demo advisor role (`X-Demo-Role: advisor`) could review a **real** student's plan (200) | Demo advisor is restricted to fictional students (404 for real plans) |
| B3 | Validation | Manual validation of 4-credit PHYS 1021 lecture + lab reported **8.0 credits** | 4.0 credits |
| B4 | Validation | Manual validation didn't know section components (lecture without its lab raised no component finding) and used different inputs than the Review Agent | Same `review_sections` as the Review Agent, with catalog-level components and a missing-component warning |
| B5 | Section compatibility | Lecture/lab pairing presented as certain, although Temple publishes no linkage (0 of 8,690 sections have `isSectionLinked`) | Pairing labeled *inferred / unverified* in review, the course list and explanations |
| B6 | Credits | 2,194 variable-credit sections planned silently at minimum credits | Warning plus explanation note with the assumed value |
| B7 | Grades | F, W and D satisfied prerequisites and requirements despite the bulletin's "Minimum grade of C-" | Non-passing grades excluded; minimum prerequisite grades and the GenEd C- rule enforced |
| B8 | Preferences | "Preferred" class times had no effect on the optimizer (penalty 0) | Sections outside preferred windows are penalized |
| B9 | Concurrency | Two simultaneous change requests both started runs (`[200, 200]`), so one overwrote the other | Atomic conditional claim; the second gets 409 before any state is written (`[200, 409]`) |
| B10 | Persistence | Preference changes were lost on the next plan (target 13 → new plan started at 15) | Persisted to the owning real student's record (13); fictional demo records stay unchanged |
| B11 | Data quality (found by a new test) | Requirement reliability counts were computed before Course Discovery downgraded rules to BLOCKED/UNAVAILABLE, so the summary was stale | Counts recomputed after the update |

## 2. Architecture weaknesses addressed (not bugs, but required by the brief)

- **No record separation**: now three explicit classes (fictional demo / real owner-only / demo advisor → fictional only) in `app/core/auth.py`, behind an `AuthProvider` seam. A `TempleSSOProvider` stub marks where Temple SSO plugs in. Tokens are stored only as SHA-256 hashes, and denials return 404 so IDs can't be probed. IDs lengthened to 80 bits.
- **No requirement reliability model**: rules are now VERIFIED / PENDING_VERIFICATION / AMBIGUOUS / UNAVAILABLE / BLOCKED. VERIFIED comes **only** from a human registry (`data/temple/verifications.json`, empty), never from the parser. Free text, needs-review layouts and catalog-year mismatches are AMBIGUOUS. Course Discovery downgrades open rules that can't progress this term.
- **Interest matches could not be recommended unless they were requirements**; there was no distinction between course roles. Added REQUIRED / DEGREE_ELECTIVE / INTEREST_ELECTIVE plus OPTIONAL_ENRICHMENT. The Interest Agent searches the whole term catalog with the same deterministic eligibility check as Discovery. Electives are capped per strategy (0 / 2 / 1) and always stated as *not* satisfying a requirement.
- **Agent activity was only a summary string**: each agent now writes a structured decision record (task, data sources, findings, recommendation, validation, unresolved), derived from its actual output. Interest Matching cross-checks requirement links and section availability from the other agents. No chain-of-thought is exposed.
- **Explanations lacked alternatives, unverified items and full provenance**: added per course: alternatives considered with the reason each lost; an explicit "still unverified" list; bulletin prerequisite text; term, CRN, campus, modality, meetings, instructor, source, retrieval time and "seats as of snapshot, not live".
- **No way to accept a tradeoff**: added `POST /plans/{id}/resolve`, which applies only solver-verified resolutions the student accepts. Soft preferences can be given up and graduation-critical courses deferred, but hard availability and the F-1 rule are refused (422). `POST /plans/{id}/regenerate` returns different combinations. The no-perfect-schedule headline is generated from the solver's conflict set (e.g. "We couldn't find a 15-credit schedule that keeps your Job and Work (campus job) hours while including PSY 3096: every eligible section of PSY 3096 conflicts with them.").
- **TUportal export without approval**: `student_approved` is now required (422 otherwise), and the UI asks for an explicit checkbox approval. The flow is still labeled MOCK and never implies registration.
- **No live-data seam**: `LiveAvailabilityAdapter` / `AuthorizedBannerAvailabilityAdapter` activate only with a Temple-issued endpoint and token (`TEMPLE_DATA_API_URL`, `TEMPLE_DATA_API_TOKEN`); otherwise they report "not configured".
- **Questionnaire gaps**: career interests, a days-off picker (none / prefer off / must be off per weekday) and a preferred-afternoons preset. Existing fields already covered multiple majors, minors and certificates, record entry, credits, campus, F-1 and weekly availability.
- **Schedule builder**: Different options, More &lt;interest&gt;, Accept tradeoff, confirmation before removing a *required* course, accepted-tradeoff chips, an F-1 panel (counted vs. additional online credits, hybrid flagged for ISSS), and category plus "pairing unverified" badges.

## 3. Files changed
Backend: `apps/api/app/core/auth.py` (new), `core/config.py`, `models/__init__.py`, `seed.py` (additive SQLite migration, catalog schema version), `domain.py`, `rules.py`, `optimizer.py`, `orchestrator.py`, `ingest/sections.py`, `adapters/course_search.py`, `adapters/catalog.py`, `agents/` (`base`, `categories` (new), `profile`, `requirements`, `discovery`, `interests`, `graduation`, `constraints`, `optimization`, `review`, `explanation`), `routers/` (`students`, `plans`, `advisor`, `integration`).
Frontend: `apps/web/src/lib/{api,types}.ts`, `components/planner/{badges,course-explainer}.tsx`, `app/onboarding/page.tsx`, `app/plan/[planId]/{page,dashboard/page,schedules/page,explain/page}.tsx`.
Data/docs/tests: `data/temple/verifications.json` (new), `docs/audit/*` (new), `tests/test_audit.py` (new), `tests/test_rules.py`, `tests/test_workflow.py`, README, demo walkthrough.

## 4. Test results
- `pytest tests -q`: **71 passed, 0 failed** (52 before the audit). New tests cover unauthorized access (anonymous, another student, demo advisor), preference persistence, the busy-plan 409, grades, lecture/lab credits, components in review, preferred times, tradeoff acceptance (soft accepted; hard and F-1 refused), deferral, regeneration, the "job on Tuesdays 1–6 PM" request, reliability statuses, interest electives never shown as requirements, decision records, explanation provenance and missing course data. One genuine defect (B11) was found by these tests and fixed.
- Frontend: `tsc --noEmit` clean, `eslint` clean, `next build` succeeds.
- Browser end-to-end (headless Chromium, real Temple data): landing → demo → workspace + decision log → dashboard → schedules → explainer → section swap validation → "job on Tuesdays and Thursdays 9–5" conflict → accept "defer PSY 3096" → explanation → approval dialog → mock export → advisor → onboarding with days-off picker and token-authenticated plan. **All steps pass, no console errors.**

## 5. Remaining limitations
- Prototype tokens live in the browser's localStorage; this is a stand-in for Temple SSO, not institutional authentication. Not FERPA-reviewed.
- Lecture/lab/recitation pairing is inferred (Temple publishes no linkage). Optional-lab courses can't be distinguished from required ones; both are flagged.
- Cross-listing metadata wasn't captured in the snapshot; same-time cross-listed sections are still mutually excluded by the time-conflict constraint.
- Registration restrictions (major, class level, permits, holds) aren't in the snapshot; review warns that TUportal enforces them.
- Seats and times are a 2026-11-03 snapshot, not live.
- Only the 2026-2027 bulletin is ingested; ≈490 prose rules are AMBIGUOUS; no rule is VERIFIED until a person records it.
- Requirement-level minimum grades beyond prerequisites and GenEd (e.g. "C- in major courses" written in prose) aren't enforced.
- The interest fallback is lexical concept matching. Claude-based semantic ranking runs only with `ANTHROPIC_API_KEY` and hasn't been exercised against the live API in this session.
- Demo spec asks for a "Computer Science certificate"; Temple has none, so the demo uses the real Data Science: Computational Analytics certificate.

## 6. Integrations still requiring Temple authorization
Temple SSO (identity plus advisor-to-student assignment), Degree Audit access, an authorized live seat/availability feed, the TUportal test environment for draft schedules, and human verification of requirement rules (department or advising office).

## 7. Running the corrected application
```bash
cd apps/api && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010      # existing SQLite DBs migrate additively
cd apps/web && npm install && echo "NEXT_PUBLIC_API_URL=http://127.0.0.1:8010" > .env.local && npm run dev
python -m pytest tests -q                                           # from the repo root, using apps/api/.venv
```

## 8. Demo walkthrough
See [docs/demo-walkthrough.md](docs/demo-walkthrough.md).
