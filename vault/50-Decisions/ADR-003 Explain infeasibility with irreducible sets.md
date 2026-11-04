# ADR-003 Explain infeasibility with irreducible sets
**Status:** accepted
**Decision:** Every hard constraint sits behind an assumption literal; on infeasibility take the solver core and shrink it with a deletion filter to an irreducible set. Each offered resolution is re-solved first. Hard availability and F-1 are never auto-relaxed; soft only with approval (`POST /plans/{id}/resolve`, 422 otherwise).
**Consequences:** "No silent violations"; extra solves per infeasible plan. See [[Optimizer (CP-SAT)]].
