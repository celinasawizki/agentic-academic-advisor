# ADR-005 One pipeline for every program
**Status:** accepted
**Decision:** No per-major code. All 435 programs share one data model; school/college differences are data (`school_rules.json`) applied by program type and degree.
**Consequences:** Parser quality limits coverage; regressions caught by `sweep_programs` and `stress_plans`. See [[School & University Rules]].
