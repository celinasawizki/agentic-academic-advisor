# Optimizer (CP-SAT)
File: `apps/api/app/optimizer.py`; driven by [[Schedule Optimization Agent]].

**Variables** — bool per eligible section; per course `y_c = Σ x_s` (≤1 section per course, one per component for lecture/lab/recitation).

**Hard (each behind an enforcement literal)** — hard availability blocks (grouped by label), credit min/max, graduation-critical courses (Graduation strategy only), requested courses, locked sections, F-1: `in_person + min(online, 3) ≥ 12`.

**Always on** — pairwise time-conflict exclusion, per-requirement caps, diversity cuts between strategies.

**Objective** — `w_req·Σpriority + w_int·Σinterest − w_soft·Σsoft_penalty − w_dev·|credits − target|`; weights per strategy (Graduation / Interest / Balance). Preferred-time windows penalize sections outside them (audit B8).

**Infeasibility** — `SufficientAssumptionsForInfeasibility()` core → deletion filter → irreducible set. "Perfect schedule" analysis hardens soft blocks to explain why not every preference fits. Each proposed resolution is re-solved before being offered. See [[ADR-003 Explain infeasibility with irreducible sets]].
