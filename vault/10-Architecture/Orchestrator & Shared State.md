# Orchestrator & Shared State
File: `apps/api/app/orchestrator.py`.

- `PlanRun.state` = student snapshot (incl. session preference changes), each agent's typed output keyed by agent name, iteration number, change history.
- Every step is an `AgentExecution` row (status, mode `llm`/`deterministic`/`llm_fallback`, timings, log, sources, decision record). The UI polls and renders these — real progress, not animation.
- Re-plan after a change starts at **Course Discovery**; earlier agents are "skipped — reused".
- Review rejection → option's course set added to exclusions → Optimization + Review re-run (bounded).
- Concurrency: change requests atomically claim the run; a second concurrent one gets **409** (audit B9).
- Preference changes persist to the owning *real* student; fictional demo records never change (audit B10).

Related: [[Agents Index]], [[Optimizer (CP-SAT)]].
