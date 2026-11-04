# ADR-001 LLMs never decide validity
**Status:** accepted
**Context:** Academic advice must be correct and auditable; LLM output can be wrong or injected.
**Decision:** LLMs only interpret (interests, change requests) and explain. Conflicts, prereqs, credits, campus, F-1 are enforced by [[Rules Engine]] and [[Optimizer (CP-SAT)]]. Every LLM path has a deterministic fallback.
**Consequences:** App fully works without an API key; LLM output must be schema-validated and filtered. See [[LLM Usage]].
