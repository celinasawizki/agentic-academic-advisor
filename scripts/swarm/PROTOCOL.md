# Swarm protocol (Temple Academic Planning AI)

Four Claude Code sessions run side by side in tmux (`scripts/swarm/start.sh`)
and coordinate as peers over cross-session messaging (`ListAgents`,
`SendMessage`). Adapted from github.com/celinasawizki/vscode-swarm-setup.

| Session name | Role |
|---|---|
| `tap-orchestrator` | Breaks down objectives, delegates, tracks status, reports to the human (or to the lead Claude session that sent the task) |
| `tap-researcher` | Investigates code, data and approaches; reports findings |
| `tap-builder` | Writes/edits code and tests |
| `tap-reviewer` | Independently verifies builder's work: reads the diff, runs tests, probes edge cases, reports bugs back to builder |

Always address peers by these exact `tap-*` names (an older, unrelated swarm uses the bare names `builder`, `reviewer`, etc.; never message those). Send real messages and wait for real replies. Never simulate another agent.

## Project rules come first

`CLAUDE.md` in the repo root is binding for every agent: LLMs never decide
validity, no student records to the LLM, nothing hardcoded per major, never
guess requirements, hard availability / F-1 never relaxed automatically,
404-not-403 auth denials, polite scraping. Add a test for each bug fixed;
workflow tests use `tests/fixtures/catalog`, not real Temple data.

## Hard limits (sessions may run with bypassed permissions)

- **No** `git commit`, `git push`, `git reset --hard`, `git checkout -- <file>`
  on files you did not change, `git clean`, branch deletion, or `rm -rf`.
  The human commits.
- **No** network scraping: never run `import_sections`, `ingest_bulletin --refresh`,
  or anything that fetches Temple or Google pages.
- Do not edit `data/temple/*` or `docs/audit/*` unless the task says so. If you
  run `python -m scripts.stress_plans`, restore the committed report with
  `git checkout docs/audit/stress-report.json` afterwards.
- Stay inside this repository.

## Who edits what

Only `tap-builder` edits code. `tap-researcher` and `tap-reviewer` are read-only on source
files (they may write scratch scripts under `/tmp` or the OS temp dir).
Before editing, builder re-reads the file; keep changes small and focused.

## Shared task board: `SWARM_STATUS.md` (repo root, gitignored)

Every task gets a row. Update your own row when you start, finish or block,
one row per edit, re-reading the file first. Status values:
`pending` · `in-progress` · `review` · `blocked` · `done`.
Only `tap-reviewer` moves a build task to `done`.

## Flow for every change

1. orchestrator adds a row and sends builder (or researcher) a scoped task.
2. builder implements + tests, sets `review`, and messages `tap-reviewer` directly
   with: files changed, what to verify, test command.
3. reviewer runs `python -m pytest tests -q` (venv: `apps/api/.venv`), reads the
   diff, tries edge cases, and checks the CLAUDE.md rules. Bugs → message
   builder with file:line + repro, set row back to `in-progress`. Clean → `done`
   and message orchestrator.
4. orchestrator reports the verified result in plain language.

Keep messages short and specific.
