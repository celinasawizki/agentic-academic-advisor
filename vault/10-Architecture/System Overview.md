# System Overview
```
Next.js (apps/web) ──REST──▶ FastAPI (apps/api) ──BackgroundTasks──▶ Orchestrator
                                                                 │
        Profile → Research → Requirements → Discovery → Interests → Graduation
              → Constraints → Optimization ⇄ Review (reject → re-optimize, max 1) → Explanation
```
- Backend: FastAPI + SQLAlchemy (SQLite default, Postgres via `DATABASE_URL`) + OR-Tools + Anthropic SDK.
- Frontend: Next.js 16 App Router, TS, Tailwind 4, shadcn/ui on Base UI. Pages: `/onboarding`, `/demo`, `/plan/[planId]` (workspace, `dashboard`, `schedules`, `explain`), `/advisor`, `/architecture`.
- Routers: `students`, `plans` (create/get/modify/preferences/resolve/regenerate/validate), `catalog`, `advisor`, `integration`.
- Adapters: snapshot course search, DB catalog, live bulletin, PDF degree audit, mock TUportal, gated live-availability seam.

Related: [[Orchestrator & Shared State]], [[Agents Index]], [[Auth & Privacy]].
Full doc: `docs/architecture.md`.
