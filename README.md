# Temple Academic Planning AI

Multi-agent academic planning and constraint-based schedule optimization for Temple University students. Built for Temple's AI Build Challenge 2026 as a hackathon prototype.

> **Prototype notice.** Planning assistance only — not an official degree audit, registration system, or immigration advice. Requirements are **parsed automatically** from the public Temple Academic Bulletin and are pending verification against a student's official degree audit. Sections are a **point-in-time snapshot** of Temple's public class search. All students in the demo are fictional.

## Coverage

| Data | Source | Count |
|---|---|---|
| Undergraduate programs | Temple Academic Bulletin, 2026-2027 catalog | **435** (230 majors, 119 minors, 86 certificates) + GenEd |
| Requirement rules | Parsed from each program's requirement tables | 8,300+ (≈490 free-text rules flagged for manual review, never guessed) |
| Undergraduate courses | Bulletin course descriptions | 6,800+ with credits, GenEd attributes and parsed prerequisite logic |
| Sections | Public class search snapshot, Spring 2027 (term 202703) | 8,690 with real meeting times, modality, seats, instructors |

Every program uses the same data model and pipeline — nothing is hardcoded per major.

**School, college and university requirements.** A program page lists only its own courses; graduation also depends on the student's school. [`data/temple/school_rules.json`](data/temple/school_rules.json) transcribes the graduation rules of all 13 undergraduate schools/colleges (e.g. Liberal Arts: 123 credits, 45 upper-level, foreign language through 1002 and a global-studies option for BAs, the professional-development seminar; Fox: the 20-course BBA business core; Klein: KLN 1001/1002 and 124 credits; CST: SCTC 1001 seminar and BA language; Public Health/Social Work: HRPR 1001; Engineering, Pharmacy, STHM, TFMA, Boyer, Education, Tyler), each with a verbatim bulletin quote, plus university rules (30-credit residency, two writing-intensive courses — the exact WI courses are read from each major's page) and program minimum grades. They are applied automatically by program type and degree (BA vs BS vs BBA). `python -m scripts.sweep_programs` runs the full pipeline for all 436 programs (last run: 436/436 complete, every major with its school layer). See [data/temple/README.md](data/temple/README.md) for provenance and [docs/integrations.md](docs/integrations.md) for limitations.

## What it does

A student completes a 7-step onboarding (any combination of Temple programs, academic records, interests in their own words, a drag-to-paint weekly availability grid, credit load, campus, F-1 status). Ten specialized agents then share one planning state:

| # | Agent | Responsibility | Engine |
|---|---|---|---|
| 1 | Academic Profile | Separates completed / in-progress / transfer work, resolves catalog year | Deterministic |
| 2 | Requirements Research | Searches the bulletin for each program (Claude web search limited to bulletin.temple.edu when a key is set, otherwise the bulletin's sitemap index), fetches the official program page and the student's school page live (robots.txt, 1 req/s, 24 h cache), re-parses them and checks every transcribed school rule's quote is still on the page | Deterministic + optional Claude search |
| 3 | Degree Requirements | Applies program **plus school/college and university** rules: required courses, "or" alternatives, lecture+lab bundles, select-N and credit groups, course ranges, GenEd attributes; no double counting without a rule | Deterministic |
| 4 | Course Discovery | Expands rules against the term's sections; filters campus, prerequisites (AND/OR logic, placement alternatives), seats, arranged courses; logs every exclusion | Deterministic |
| 5 | Interest Matching | Scores course descriptions against free-text interests | Claude (schema-validated) or concept/keyword fallback |
| 6 | Graduation Planning | Prerequisite chains, critical courses, pace and risks | Deterministic |
| 7 | Scheduling & Constraints | Typed hard / soft / academic / immigration constraints; pre-checks | Deterministic |
| 8 | Schedule Optimization | Google OR-Tools CP-SAT, three strategies, lecture/lab/recitation components, solver-computed conflict sets | CP-SAT |
| 9 | Academic Review | Independent re-verification; can reject → orchestrator re-optimizes | Deterministic |
| 10 | Student Explanation | Per-course reasons, tradeoffs, unresolved issues | Templated + optional Claude summary |

Language models interpret and explain; **they never decide validity**. Conflicts, prerequisites, credits, campus and the F-1 counting rule are enforced by code and by the solver.

### Highlights

- **No silent violations.** When no schedule satisfies every preference, CP-SAT runs with each hard constraint behind an assumption literal, returns the responsible assumptions, and a deletion filter shrinks them to an **irreducible conflicting set**. Each resolution (relax a soft preference, change a hard block, defer a course, reduce credits) is re-solved to confirm it works before it is offered.
- **Real course structure.** Courses with separate lecture, lab and recitation sections get one section of each component, with clashes checked between them and credits counted once.
- **Hard vs. soft vs. academic vs. immigration** constraints are distinct types. Soft preferences are relaxed only with student approval; hard availability is never scheduled over; the F-1 rule cannot be overridden by preferences.
- **F-1 rule done carefully.** At most one online course / 3 online credits *count* toward the 12-credit full course of study. Extra online enrollment is allowed but not counted. Hybrid ("Mix of In-person and Online") is not assumed to be in-person and is flagged for ISSS confirmation.
- **Conversational changes** ("Give me Fridays off", "I got a job on Tuesdays and Thursdays from 9 to 5") are parsed into a typed change set (Claude structured output or a deterministic parser), applied, and the affected agents re-run. Assumptions (e.g. unstated work hours) are surfaced.
- **Transparency.** Every recommendation shows which bulletin rule it may satisfy (pending verification), how it matches interests (AI suggestion vs. concept match), why this section beat the others, and provenance (CRN, snapshot date, bulletin link).
- **Mock TUportal adapter** saves draft schedules to a clearly labeled mock environment. Nobody is ever registered.

### Trust, safety and transparency (audit, Nov 2026)

- **Record separation**: fictional demo students are shared; real student records are owner-only (per-student token standing in for Temple SSO, behind a pluggable `AuthProvider`); the demo advisor role sees fictional students only. See [AUDIT_REPORT.md](AUDIT_REPORT.md).
- **Requirement reliability**: VERIFIED (human registry only) / PENDING VERIFICATION / AMBIGUOUS / UNAVAILABLE / BLOCKED.
- **Course roles**: Required course / Degree elective / Interest-based elective (never counted as a requirement) / Optional enrichment.
- **Decision log**: each agent records task, sources, findings, recommendation, validation and unresolved concerns from its real output.
- **Tradeoffs**: students accept solver-verified resolutions (soft preferences, deferring a course, fewer credits); hard availability and F-1 rules are never relaxed automatically. Mock TUportal export requires explicit approval.

## Repository layout

```
apps/api        FastAPI + SQLAlchemy + OR-Tools + Anthropic SDK
  app/agents    ten agents, LLM wrapper, shared context
  app/ingest    bulletin requirement/course/prerequisite parsers, section normalization
  app/adapters  course search (snapshot), requirements catalog, degree audit PDF, TUportal (mock)
  app/rules.py  deterministic rules engine
  app/optimizer.py  CP-SAT model and conflict analysis
  app/orchestrator.py  state machine over PlanRun.state
  scripts/      polite crawlers: ingest_bulletin.py, import_sections.py
apps/web        Next.js 16 (App Router) + TypeScript + Tailwind 4 + shadcn/ui (Base UI) + Lucide
data/temple     programs.json, courses.json, sections-202703.json, students.json (fictional)
docs            architecture, integrations, demo walkthrough
tests           pytest: parsers, rules, optimizer, HTTP workflow (synthetic fixture in tests/fixtures)
```

## Running locally

Requirements: Python 3.12+ and Node 22+.

```bash
cp .env.example .env              # optional: add ANTHROPIC_API_KEY

# API
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000  # creates SQLite and loads data/temple on first start (~3 s); later schema changes migrate additively

# Web (new terminal)
cd apps/web
npm install
echo "NEXT_PUBLIC_API_URL=http://127.0.0.1:8000" > .env.local
npm run dev                       # http://localhost:3000
```

The API reloads the catalog automatically whenever files in `data/temple` change (students and plans are kept), and adds new columns to existing SQLite databases automatically. Real students created through onboarding receive an access token stored in the browser; without it their records return 404.

Without `ANTHROPIC_API_KEY` every agent uses its deterministic fallback and the workspace labels each agent "Deterministic". With a key, Interest Matching, Explanation and change-request parsing call `claude-opus-5-5` with schema-validated structured outputs and server-side refusal fallbacks.

### Terminal view of what's running

```bash
./scripts/dev-swarm.sh        # tmux session on its own socket: agents feed | API | web
./scripts/dev-swarm.sh stop
```

The top pane (`scripts/watch_agents.py`) streams every agent execution the orchestrator persists — start/finish, duration, research log lines and the bulletin URLs each agent cited.

### Refreshing Temple data

```bash
cd apps/api
python -m scripts.ingest_bulletin --refresh   # ~20 min at 1 request/second; caches pages in data/temple/.cache
python -m scripts.ingest_bulletin             # re-parse from cache only (no network) after parser changes
python -m scripts.import_sections 202703      # section snapshot; run only with permission
```

### Tests

```bash
source apps/api/.venv/bin/activate
python -m pytest tests -q
```

Covers bulletin parsing (required rows, alternatives, bundles, select-N and credit groups, section-header selects, alternative tracks, cross-listings), prerequisite parsing (AND/OR, placement alternatives, grade annotations), requirement matching (bundles, credits, ranges, GenEd attributes, double counting), prerequisite verification (in-progress ≠ completed), conflicts, hard/soft constraints, F-1 counting, lecture/lab components, select-one caps, infeasibility with minimal conflict sets, schedule diversity, natural-language change parsing, upload validation, consent, deletion, mock TUportal export, and the full planning workflow over HTTP. Workflow tests run against a small synthetic fixture so they stay deterministic.

## Demo

See [docs/demo-walkthrough.md](docs/demo-walkthrough.md). Short version: open `/demo`, run **Lina Haddad** (Psychology BA, Entrepreneurship minor, Data Science certificate, F-1), watch the agents, open **Schedules**, then type "I got a job on Tuesdays and Thursdays from 9 to 5" — every open section of Research Methods (PSY 3096) then collides with one of her jobs, and the solver names the conflicting constraints and offers verified fixes. Priya (Computer Science BS) shows lecture + lab scheduling; or onboard any of the 435 programs.

## Privacy and security

- Consent required before records are processed; uploads limited to PDFs ≤ 5 MB, parsed in memory, never stored or logged.
- Student education records are **not** sent to the LLM (`LLM_MAY_RECEIVE_STUDENT_RECORDS=false`); only catalog text, interest text, and de-identified schedule facts are.
- Untrusted text is wrapped as data, LLM output is schema-validated and filtered against the dataset.
- API keys are server-side only. Students can delete their records (`DELETE /api/students/{id}` removes plans, agent logs, options and validations).
- The advisor view uses a demo-only role header. Production requires Temple SSO and advisor-student assignment checks. This prototype is not FERPA-certified.
- Temple data was collected politely: robots.txt respected for the bulletin, 1 request/second, identifying user agent, local cache so re-parsing never re-hits Temple. At plan time the Requirements Research Agent reads only the public bulletin pages for the student's own programs and school (same politeness rules, 24-hour cache; `LIVE_BULLETIN_RESEARCH=false` turns this off). Only program names are used as search queries — never student data. Google is not scraped (its terms forbid it); the bulletin's own search is disallowed by robots.txt, so the agent ranks the bulletin's sitemap, or uses Claude's web search tool restricted to bulletin.temple.edu when an API key is configured.

## Known limitations

Documented in [docs/integrations.md](docs/integrations.md): only the current (2026-2027) bulletin is ingested — earlier catalog years live in Temple's archives, which robots.txt excludes; ≈490 free-text rules (e.g. foreign-language placement, "one additional course at the Foundation Level") need manual review; section data is a snapshot; Degree Audit and TUportal are not connected; non-Main campuses are excluded from scheduling.
