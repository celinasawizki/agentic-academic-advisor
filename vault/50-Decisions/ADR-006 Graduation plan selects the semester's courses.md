# ADR-006 Graduation plan selects the semester's courses
**Status:** accepted (2026-11-03)
**Context:** A real student (a Psychology BA with an EIM minor and Programming cert) reported that the planner kept scheduling classes they didn't need. The requirement-driven optimizer picks courses by degree priority and interest, which ignored the semester-by-semester E-Graduation Plan the student had already built with their advisor.
**Decision:** Real students must upload their E-Graduation Plan (PDF) before schedules are proposed: onboarding step "Grad plan", plus `POST /api/plans` returns 422 without courses for the planning term. The plan's included courses for that term are the **only** courses scheduled. The solver chooses sections. Requirement caps, free-elective limits and graduation-critical fill-ins don't apply (`build_plan_model`, `ScheduleModel(plan_mode=True)`).
- The parser (`app/adapters/grad_plan.py`) is local, rule-based and position-aware, because the grid's columns interleave in plain text extraction. Nothing goes to the LLM, and the name/TUID is dropped.
- Lines without a course code ("GenEd Science/Tech course (GS2)") stay open slots and are never resolved by guessing ([[ADR-004 Never guess requirements]]). A "PSY 2000-level … - 2104" hint is offered for the student to confirm, never scheduled on its own.
- "WINTER BREAK" items in a spring column default to not included.
- A plan course that is blocked (prereq, not offered) makes the model infeasible, and the conflict set says "Include X (your graduation plan)". No substitute is invented; the student can defer it ([[ADR-003 Explain infeasibility with irreducible sets]]).
- Sections full in the snapshot stay schedulable for plan courses, flagged `seats_full` with a waitlist warning, because snapshot seats aren't live.
- Alternate options, review rejections and "Different options" vary **sections** (section-id exclusion sets) since courses are fixed.
**Consequences:** Demo students are unaffected. `settings.require_grad_plan` (default true) is turned off by the program sweep, the stress test and most workflow tests to keep exercising requirement-driven planning. Tests: `tests/test_grad_plan.py`.
