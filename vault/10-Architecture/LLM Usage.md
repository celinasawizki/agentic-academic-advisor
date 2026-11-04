# LLM Usage
File: `apps/api/app/agents/llm.py` — the only Claude entry point. Model `claude-opus-5-5` (`ANTHROPIC_MODEL`).

- `client.beta.messages.parse` with Pydantic schema, `effort="low"`, server-side refusal fallback.
- Used by: [[Interest Matching Agent]], [[Student Explanation Agent]] summary, change-request parsing, and web search limited to bulletin.temple.edu in [[Requirements Research Agent]].
- Untrusted text wrapped in `<untrusted_data>`; outputs filtered (unknown course codes dropped, scores clamped).
- Any error/refusal/missing key → `None` → deterministic path. App must run with no key.
- Student education records never sent ([[Auth & Privacy]]).
