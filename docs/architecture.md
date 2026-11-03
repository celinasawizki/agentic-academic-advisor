# Architecture

```
 Next.js (apps/web)                          FastAPI (apps/api)
 ┌───────────────────────┐   REST/JSON   ┌──────────────────────────────────────────────┐
 │ Onboarding wizard     │──────────────▶│ /api/students  /api/degree-audit/parse       │
 │ Agent workspace (poll)│◀──────────────│ /api/plans (create, get, modify, preferences,│
 │ Dashboard / Schedules │               │            validate)                          │
 │ Explanation / Advisor │               │ /api/integration  /api/advisor               │
 └───────────────────────┘               └───────────────┬──────────────────────────────┘
                                                         │ BackgroundTasks
                                          ┌──────────────▼──────────────┐
                                          │ Orchestrator (state machine)│
                                          │ PlanRun.state = shared state│
                                          └──────────────┬──────────────┘
      ┌────────────┬─────────────┬──────────────┬────────┴─────┬──────────────┬─────────────┐
   Profile → Requirements → Discovery → Interests → Graduation → Constraints → Optimization
                                                                                   │  ▲
                                                                          Review ──┘  │ reject → revise (max 1)
                                                                             │
                                                                        Explanation
 Adapters: DemoFixtureCourseSearchAdapter · DbCatalogAdapter · PDF degree-audit parser · MockTUportalAdapter
 Engines:  rules.py (deterministic)  ·  optimizer.py (OR-Tools CP-SAT)  ·  agents/llm.py (Claude, optional)
```

## Shared planning state

`PlanRun.state` holds the student snapshot (including preferences changed during the session), each agent's typed output keyed by agent name, the iteration number and the change history. Each agent step is also an `AgentExecution` row (status, mode, timings, log, sources, error). The UI polls `GET /api/plans/{id}` and renders those rows directly, so the workspace shows real execution, not an animation.

Re-planning after a change starts at `course_discovery` (exclusions and boosts can change discovery and interest scores); earlier agents are recorded as "skipped — reused".

## Agent collaboration

Agents communicate only through typed state, never free-form chat:

- Discovery marks prerequisite-blocked courses; Interest Matching flags high-interest blocked courses; Explanation turns that into "matches your interests, but you have not completed its prerequisite — here are eligible alternatives".
- Graduation marks critical courses; Constraints enforces only those with an eligible section this term (the rest become pre-check warnings); the Graduation Priority strategy requires them.
- Review independently re-checks each option with `rules.py` (not optimizer state). A rejection adds the option's course set to an exclusion list and the orchestrator re-runs Optimization and Review.

## Optimization model (CP-SAT)

Variables: one boolean per eligible section, one per course (`y_c = Σ x_s`, at most one section per course).

Hard constraints (each behind an enforcement literal so infeasibility can be explained):
- availability blocks marked hard (grouped by label), credit min, credit max
- graduation-critical courses (Graduation Priority strategy only), student-requested courses, locked sections
- F-1: `in_person + min(online, 3) ≥ 12` (hybrid excluded unless configured)

Always-on: pairwise time-conflict exclusion, per-requirement caps (no more courses than a requirement still needs), and diversity cuts so later strategies differ from earlier ones.

Objective: `w_req·Σ priority + w_int·Σ interest − w_soft·Σ soft_penalty − w_dev·|credits − target|`, with weights per strategy (Graduation, Interest, Balance).

Infeasibility: `SufficientAssumptionsForInfeasibility()` gives a core; a deletion filter re-solves without each member to obtain an irreducible set. "Perfect schedule" analysis temporarily turns soft availability blocks into hard ones to explain why every preference cannot be met at once. Every proposed resolution is re-solved to confirm feasibility.

## LLM usage

`agents/llm.py` calls `client.beta.messages.parse` with a Pydantic schema, `output_config.effort="low"`, and `fallbacks="default"` (server-side refusal fallback). Untrusted text is wrapped in `<untrusted_data>` and the system prompt forbids following embedded instructions. Outputs are filtered (unknown course codes dropped, scores clamped). Any error, refusal or missing key returns `None` and the agent uses its deterministic path; the execution record shows `llm`, `deterministic`, or `llm_fallback`.

## Data model

`ResearchSource, AcademicTerm, AcademicProgram, ProgramRequirement, Course, CourseSection, Student, TranscriptEntry, DegreeAudit, StudentInterest, AvailabilityBlock, PlanRun, SchedulingConstraint, AgentExecution, ScheduleOption, ScheduleCourse, ValidationResult, AdvisorReview, IntegrationStatus` — see `apps/api/app/models/__init__.py`. Sections have stable IDs (`{term}-{course}-{section}`); requirements carry catalog year, verification status and source; sections carry data source and retrieval time.
