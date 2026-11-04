# CLAUDE.md

Temple Academic Planning AI — a multi-agent academic planner and CP-SAT schedule optimizer for Temple University students (hackathon prototype). FastAPI backend in `apps/api`, Next.js 16 frontend in `apps/web`, real Temple data snapshot in `data/temple`. Project knowledge lives in the Obsidian vault at `vault/` (start at `vault/00-Home/Home.md`).

## Commands

```bash
# API (Python 3.12+)
cd apps/api && source .venv/bin/activate
uvicorn app.main:app --port 8000          # creates/migrates SQLite, loads data/temple

# Web (Node 22+)
cd apps/web && npm run dev                # needs .env.local: NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
npx tsc --noEmit && npm run lint && npm run build

# Tests (from repo root, venv active)
python -m pytest tests -q
python -m pytest tests/test_school_layers.py -q

# Whole-pipeline checks (from apps/api)
python -m scripts.sweep_programs          # every program through the pipeline → docs/audit/program-sweep.json
python -m scripts.stress_plans --n 120    # randomized students + invariants → docs/audit/stress-report.json

# Terminal view: agents feed | API | web
./scripts/dev-swarm.sh   /   ./scripts/dev-swarm.sh stop
```

## Architecture in one paragraph

`app/orchestrator.py` runs ten agents (`app/agents/*.py`) as a state machine over `PlanRun.state`; each step is persisted as an `AgentExecution` row the UI polls via `GET /api/plans/{id}`. Order: Profile → Requirements Research → Degree Requirements → Course Discovery → Interest Matching → Graduation → Constraints → Optimization → Review (can reject → one re-optimize) → Explanation. Re-plans after a change start at Course Discovery. Agents communicate only through typed state. Deterministic engines: `app/rules.py` (requirements, prereqs, grades, F-1 counting) and `app/optimizer.py` (OR-Tools CP-SAT, assumption literals + deletion filter for irreducible conflict sets). `app/agents/llm.py` is the only Claude entry point.

## Rules that must not be broken

- **LLMs never decide validity.** Conflicts, prerequisites, credits, campus and F-1 are enforced in `rules.py` / the solver. LLM output is schema-validated, filtered against the dataset, and every LLM path has a deterministic fallback (`None` → fallback). The app must work with no `ANTHROPIC_API_KEY`.
- **No student education records to the LLM** (`LLM_MAY_RECEIVE_STUDENT_RECORDS=false`). Untrusted text is wrapped in `<untrusted_data>`.
- **Nothing hardcoded per major.** All 435 programs share one data model and pipeline. School/college rules come from `data/temple/school_rules.json` with verbatim bulletin quotes.
- **Never guess requirements.** Unparseable prose becomes `kind: "manual"` / AMBIGUOUS. VERIFIED comes only from `data/temple/verifications.json` (human registry), never from the parser.
- **Hard availability and the F-1 rule are never relaxed automatically**; soft preferences only with student approval; every offered resolution is re-solved before it is shown.
- **Auth/record separation** (`app/core/auth.py`): fictional demo students are shared; real students are owner-only via token; demo advisor sees fictional students only. Denials return 404, not 403.
- **Mock TUportal only.** Export requires `student_approved`; never imply registration.
- **Polite scraping**: robots.txt, 1 req/s, identifying UA, cache in `data/temple/.cache` (gitignored). Do not run `import_sections` or `ingest_bulletin --refresh` without the user's permission. Never scrape Google.

## Conventions

- Next.js 16 has breaking changes — read `apps/web/AGENTS.md` and `node_modules/next/dist/docs/` before writing frontend code. UI is shadcn/ui on Base UI + Tailwind 4 + Lucide.
- Frontend types mirror the API in `apps/web/src/lib/types.ts`; calls go through `apps/web/src/lib/api.ts`. Change both when an API response shape changes.
- Schema changes: SQLite migrates additively in `app/seed.py` (bump the catalog schema version when catalog shape changes).
- Workflow tests use the synthetic fixture in `tests/fixtures/catalog`, not real Temple data, so they stay deterministic. Add a test for each bug fixed.
- Section IDs are stable: `{term}-{course}-{section}`. Lecture/lab pairing is *inferred* — always label it unverified.
- Prototype notice wording (planning assistance only, pending verification, fictional students) must stay on user-facing surfaces.

## Where to record knowledge

Update the vault, not this file, for decisions (`vault/50-Decisions/`), open issues (`vault/60-Issues/`) and session notes. Keep this file to commands and invariants.
